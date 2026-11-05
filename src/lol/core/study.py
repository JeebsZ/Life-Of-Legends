"""Study: flashcard decks, a notes -> cards parser, quiz question generators, an exam/learn run,
Leitner spaced repetition and capped Scholar XP. Pure logic: no Flet, no clock, no I/O.

Flow: notes (typed, pasted, CSV/TSV or read from a photo) -> `parse_notes` / `parse_table` ->
DRAFT cards with a confidence flag -> the player accepts / edits / rejects each one ->
`StudyMixin.add_cards`. A study session: `build_quiz` -> `StudyRun` (answer, learn-mode
repeats, time limit) -> `StudyMixin.finish_study` (spaced repetition + XP, once per run).

Question kinds: "mc" (pick the definition of a term, 4 options), "tf" (is this the term's
definition?), "fill" (type the blanked key word of the definition), "type" (type the answer)
and "flip" (classic card: know / don't know). Every generator takes a `random.Random`, so a
seed gives the same quiz.

Spaced repetition: Leitner boxes 0..5. A first-try correct answer moves the card up one box
(due again after BOX_DAYS[box] days); a miss drops it to box 0, due today, so it leads the
next session. Learn-mode repeats never promote a card twice in one run.
"""

from __future__ import annotations

import csv
import io
import random
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from lol.core.models import Completion, Quest, StudyCard, StudyDeck, StudySession

if TYPE_CHECKING:
    from lol.core.models import SaveData

# --- Balance (working choices: tweak here) ---------------------------------------------------
STUDY_PATH = "scholar"
QUESTION_KINDS = ("mc", "tf", "fill", "type", "flip")
QUIZ_KINDS = ("mc", "tf", "fill", "type")  # the exam simulator's mix
STUDY_MODES = ("exam", "learn", "flip", "review", "weak")  # review = due today
MC_OPTIONS = 4  # multiple choice needs this many cards (else it falls back to true/false)
BOX_DAYS = (0, 1, 2, 4, 8, 16)  # Leitner box -> days until the card is due again
MAX_BOX = len(BOX_DAYS) - 1
MASTERED_BOX = 4
STUDY_XP_PER_CARD = 1  # per card answered on the first try (right or wrong: effort counts)
STUDY_SESSION_XP_CAP = 15
STUDY_MIN_CARDS = 3  # shorter sessions give no XP
STUDY_REPEAT_MULT = (1.0, 0.5, 0.25)  # nth session on the SAME deck the same day; then 0
STUDY_DAILY_XP_CAP = 45  # all study XP in one day
STUDY_COINS = 2  # first rewarded session per deck per day
STUDY_DAILY_COIN_CAP = 6
STRONG_SCORE = 0.8  # >= this share right (and >= STUDY_MIN_CARDS) = a strong-score effect
DECK_COLORS = ("#7FB2FF", "#4FE3F0", "#A78BFA", "#5EEAB0", "#FFB347", "#F08CB4", "#FF8A5B")
MAX_TERM_CHARS = 120
MAX_DEF_CHARS = 1000
BLANK = "_____"

STOPWORDS = frozenset(["a", "an", "the", "and", "or", "but", "nor", "so", "yet", "of", "to", "in", "on", "at", "by", "for", "with", "from", "into", "onto", "upon", "over", "under", "about", "as", "is", "are", "was", "were", "be", "been", "being", "am", "do", "does", "did", "done", "has", "have", "had", "having", "it", "its", "it's", "this", "that", "these", "those", "there", "their", "they", "them", "he", "she", "his", "her", "him", "we", "our", "us", "you", "your", "i", "me", "my", "mine", "not", "no", "yes", "if", "then", "than", "when", "while", "which", "who", "whom", "whose", "what", "where", "why", "how", "all", "any", "some", "each", "every", "both", "either", "neither", "one", "two", "also", "very", "can", "could", "may", "might", "must", "shall", "should", "will", "would", "just", "only", "such", "same", "other", "more", "most", "less", "least", "much", "many", "few", "own", "out", "up", "down", "off", "again", "once", "here", "used", "use", "uses", "using", "called", "known", "like", "e.g", "i.e", "etc", "via", "per"])


# --- text helpers -----------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Lowercase, accents stripped, punctuation dropped, spaces collapsed, leading article
    removed: the form answers are compared in."""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    t = re.sub(r"[^\w\s]", " ", t).replace("_", " ")
    t = " ".join(t.split())
    return re.sub(r"^(the|a|an) ", "", t)


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance (insert / delete / substitute = 1)."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def typo_allowance(length: int) -> int:
    """Typos forgiven for an answer of this (normalized) length."""
    if length <= 3:
        return 0
    if length <= 6:
        return 1
    if length <= 12:
        return 2
    return round(length * 0.15)


def check_text(given: str, expected: str) -> str:
    """'exact' | 'close' (a small typo, counts as right) | 'wrong'. Case, accents,
    punctuation and a leading article never matter. `expected` may list alternatives with
    '/' or ';' (e.g. 'car / automobile')."""
    g = normalize(given)
    if not g:
        return "wrong"
    options = [normalize(expected)]
    if re.search(r"[/;]", expected):
        options += [normalize(p) for p in re.split(r"[/;]", expected) if normalize(p)]
    best = "wrong"
    for e in options:
        if not e:
            continue
        if g == e:
            return "exact"
        if edit_distance(g, e) <= typo_allowance(len(e)):
            best = "close"
    return best


# --- notes -> draft cards -----------------------------------------------------------------------
CONFIDENCES = ("high", "medium", "low")


@dataclass
class Draft:
    """A card the parser proposes; the player checks it before it is saved."""

    term: str
    definition: str
    confidence: str = "high"  # high | medium | low
    source: str = ""  # tab | equals | dash | colon | qa | heading | bold | pair | csv
    line: int = 0  # 1-based line in the notes where it starts
    duplicate: bool = False  # same term as another draft or a card in the deck


@dataclass
class ParseResult:
    drafts: list[Draft] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # lines that became no card


_BULLET = re.compile(r"^\s*(?:[-*+•◦▪‣·→>]|\(?\d{1,3}[.)]|\(?[a-zA-Z]\))\s+")
_NUMBERED = re.compile(r"^\s*\(?\d{1,3}[.)]\s+")
_MD_HEADING = re.compile(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$")
_BOLD_LINE = re.compile(r"^\s*(\*\*|__)(.+?)\1\s*:?\s*$")
_BOLD_START = re.compile(r"^(\*\*|__)(.+?)\1\s*(.*)$")
_Q = re.compile(r"^\s*(?:Q|Question)\s*\d*\s*[:.)]\s*(.+)$", re.IGNORECASE)
_A = re.compile(r"^\s*(?:A|Ans|Answer)\s*\d*\s*[:.)]\s*(.*)$", re.IGNORECASE)
_QA_INLINE = re.compile(r"^\s*(?:Q|Question)\s*[:.)]\s*(.+?)\s+(?:A|Ans|Answer)\s*[:.)]\s*(.+)$",
                        re.IGNORECASE)
_SEPARATORS = ((" = ", "equals"), (" - ", "dash"), (" – ", "dash"), (" — ", "dash"),
               (" -- ", "dash"), (" : ", "colon"))


def _clean(text: str) -> str:
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)  # inline bold
    return " ".join(text.replace("\t", " ").split()).strip(" *_")


def _split_pair(body: str) -> tuple[str, str, str] | None:
    """(term, definition, source) at the earliest separator, or None."""
    if "\t" in body.strip():
        left, right = body.strip().split("\t", 1)
        if left.strip() and right.strip():
            return left, right, "tab"
    best: tuple[int, int, str] | None = None
    for sep, src in _SEPARATORS:
        i = body.find(sep)
        if i > 0 and (best is None or i < best[0]):
            best = (i, len(sep), src)
    m = re.search(r"(?<!\d):(?!\d)|(?<=\d):(?=\s)", body)  # a colon that is not a time 10:30
    if m and m.start() > 0 and (best is None or m.start() < best[0]):
        best = (m.start(), 1, "colon")
    if best is None:
        return None
    i, n, src = best
    return body[:i], body[i + n:], src


def _is_item(line: str) -> bool:
    """A line that starts a new term/definition pair (short term before a separator)."""
    pair = _split_pair(line)
    return bool(pair and pair[1].strip() and len(_clean(pair[0]).split()) <= 6)


def _term_ok(term: str) -> bool:
    return 0 < len(term) <= MAX_TERM_CHARS and len(term.split()) <= 12


def _confidence(term: str, definition: str) -> str:
    if len(term.split()) <= 6 and len(definition) >= 2:
        return "high"
    return "medium"


def _looks_like_title(text: str) -> bool:
    """A short line that could be a term on its own (the definition follows below)."""
    words = text.split()
    return 0 < len(words) <= 6 and not text.rstrip().endswith((".", "?", "!", ",", ";"))


def parse_notes(text: str) -> ParseResult:
    """Find term/definition pairs in free-form notes. Formats:
    'term - definition' (also – — --), 'term: definition', 'term = definition',
    'term<TAB>definition', 'Q: … A: …' (same line or next lines), bullets and numbered lists
    ('1. term - def'), a heading ('# Term', '**Term**', 'Term:' or a numbered short line)
    followed by its definition lines, '**Term** definition', and - low confidence - a plain
    short line followed by a longer one. Indented / lowercase lines continue the previous
    definition. Lines that fit nothing are returned in `skipped`."""
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = ParseResult()
    n = len(lines)
    i = 0
    last: Draft | None = None

    def add(term: str, definition: str, conf: str, src: str, at: int) -> Draft | None:
        term, definition = _clean(term), _clean(definition)
        term = term.rstrip(":-–— ").strip()
        if not term or not definition or not _term_ok(term):
            return None
        d = Draft(term, definition[:MAX_DEF_CHARS], conf, src, at + 1)
        out.drafts.append(d)
        return d

    def follow(start: int) -> tuple[str, int]:
        """Definition lines after a heading: up to a blank line or the next item."""
        parts: list[str] = []
        j = start
        while j < n and lines[j].strip():
            s = lines[j]
            if parts and (_Q.match(s) or _MD_HEADING.match(s) or _BOLD_LINE.match(s)
                          or _is_item(_BULLET.sub("", s, 1))):
                break
            if parts and parts[-1].endswith((".", "!", "?")) and s[:1] not in (" ", "\t") \
                    and not s.strip()[:1].islower():
                break  # a finished sentence, then a new capitalised line: a new item
            if not parts and (_MD_HEADING.match(s) or _BOLD_LINE.match(s) or _Q.match(s)):
                break
            if not parts and _split_pair(_BULLET.sub("", s, 1)):
                break
            parts.append(_BULLET.sub("", s, 1).strip())
            j += 1
        return " ".join(parts), j

    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            last = None
            i += 1
            continue
        # Q/A on one line, or Q then an A line (answer may continue on the next lines)
        if m := _QA_INLINE.match(s):
            last = add(m.group(1), m.group(2), "high", "qa", i)
            i += 1
            continue
        if m := _Q.match(s):
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and (a := _A.match(lines[j])):
                parts = [a.group(1)]
                k = j + 1
                while (k < n and lines[k].strip() and not _Q.match(lines[k])
                       and not _A.match(lines[k])
                       and (lines[k][:1] in (" ", "\t") or lines[k].strip()[:1].islower())):
                    parts.append(lines[k].strip())
                    k += 1
                last = add(m.group(1), " ".join(parts), "high", "qa", i)
                i = k
                continue
        # markdown / bold heading followed by its definition
        heading = _MD_HEADING.match(s) or _BOLD_LINE.match(s)
        if heading:
            title = heading.group(heading.lastindex or 1)
            definition, j = follow(i + 1)
            if definition:
                last = add(title, definition, "medium", "heading", i)
                i = j
                continue
            out.skipped.append(s)
            last = None
            i += 1
            continue
        # continuation of the previous definition (indented or starts lowercase)
        if last is not None and (raw[:1] in (" ", "\t") or s[:1].islower()) \
                and not _BULLET.match(raw) and not _split_pair(s):
            last.definition = f"{last.definition} {_clean(s)}"[:MAX_DEF_CHARS]
            i += 1
            continue
        numbered = bool(_NUMBERED.match(s))
        body = _BULLET.sub("", raw, 1) if _BULLET.match(raw) else raw
        # **Term** definition / **Term** - definition
        if bm := _BOLD_START.match(body.strip()):
            after = bm.group(3).strip()
            rest = re.sub(r"^[-–—=:]+\s*", "", after)
            if rest:
                last = add(bm.group(2), rest, "high" if rest != after else "medium", "bold", i)
                i += 1
                continue
        pair = _split_pair(body)
        if pair:
            term, definition, src = pair
            if not definition.strip():  # 'Term:' then the definition below
                definition, j = follow(i + 1)
                if definition:
                    last = add(term, definition, "medium", "heading", i)
                    i = j
                    continue
            elif (d := add(term, definition, _confidence(_clean(term), _clean(definition)),
                           src, i)):
                last = d
                i += 1
                continue
        # a short line followed by its definition
        title = _clean(body)
        nxt = lines[i + 1].strip() if i + 1 < n else ""
        if _looks_like_title(title) and len(_clean(_BULLET.sub("", nxt, 1)).split()) > len(
                title.split()):
            definition, j = follow(i + 1)
            if definition and len(definition) > len(title):
                last = add(title, definition, "medium" if numbered else "low",
                           "heading" if numbered else "pair", i)
                i = j
                continue
        out.skipped.append(s)
        last = None
        i += 1
    return out


def parse_table(text: str) -> ParseResult:
    """CSV / TSV (term, definition[, hint]) -> drafts. The delimiter is sniffed from the first
    line (a tab wins); a 'term,definition' header is skipped. Text with neither a tab nor a
    comma goes through parse_notes instead."""
    body = str(text or "").lstrip("﻿")
    first = next((ln for ln in body.splitlines() if ln.strip()), "")
    if "\t" in first:
        delim = "\t"
    elif "," in first:
        delim = ","
    else:
        return parse_notes(body)
    out = ParseResult()
    for n, row in enumerate(csv.reader(io.StringIO(body), delimiter=delim), 1):
        cells = [_unformula(c).strip() for c in row]
        if not any(cells):
            continue
        if n == 1 and [c.lower() for c in cells[:2]] in (["term", "definition"],
                                                         ["question", "answer"]):
            continue
        if len(cells) >= 2 and cells[0] and cells[1] and _term_ok(cells[0]):
            out.drafts.append(Draft(cells[0], cells[1][:MAX_DEF_CHARS], "high", "csv", n))
        else:
            out.skipped.append(delim.join(row))
    return out


def mark_duplicates(drafts: Sequence[Draft], existing_terms: Iterable[str] = ()) -> None:
    """Flag drafts whose term repeats an earlier draft or a card already in the deck."""
    seen = {normalize(t) for t in existing_terms}
    for d in drafts:
        key = normalize(d.term)
        d.duplicate = key in seen
        seen.add(key)


def _unformula(cell: str) -> str:
    """Undo the CSV formula guard (a leading apostrophe before = + - @)."""
    return cell[1:] if cell[:2] in ("'=", "'+", "'-", "'@") else cell


def _formula_safe(cell: str) -> str:
    return "'" + cell if cell[:1] in ("=", "+", "-", "@") else cell


def deck_to_text(cards: Iterable[StudyCard], delimiter: str = ",") -> str:
    """Export as CSV (',') or TSV ('\\t'): a 'term,definition' header, one card per row.
    Cells that a spreadsheet would run as a formula get a leading apostrophe."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    w.writerow(("term", "definition"))
    for c in cards:
        w.writerow((_formula_safe(c.term), _formula_safe(c.definition)))
    return buf.getvalue()


# --- photo -> text (the OCR boundary) -------------------------------------------------------------
@runtime_checkable
class TextRecognizer(Protocol):
    """Image path -> the text in it. May be slow (call it off the UI thread) and may raise;
    the screen treats an exception or "" as "nothing read" and offers typing instead."""

    name: str

    def recognize(self, image_path: str) -> str: ...


class ManualTextRecognizer:
    """The default: no engine. The player pastes or types the text themselves."""

    name = "Manual"

    def recognize(self, image_path: str) -> str:
        return ""


# --- questions ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Question:
    kind: str  # see QUESTION_KINDS
    card_id: str
    prompt: str  # the big text: a term, a definition with a blank, or what to answer
    answer: str  # the right answer as text
    options: tuple[str, ...] = ()  # mc: the options; tf: ("True", "False")
    correct: int = -1  # mc / tf: index of the right option
    context: str = ""  # small label above the prompt (e.g. the term for a fill-in)
    statement: str = ""  # tf: the definition being judged
    back: str = ""  # flip: the back of the card


@dataclass(frozen=True)
class Grade:
    correct: bool
    close: bool = False  # right, with a forgiven typo
    expected: str = ""


def _words(text: str) -> int:
    return len(text.split())


def pick_distractors(card: StudyCard, pool: Sequence[StudyCard], k: int,
                     rng: random.Random) -> list[str]:
    """k other definitions that look like the answer (shared tags, similar length), unique
    and never equal to it. Fewer than k when the deck can't supply them."""
    target = normalize(card.definition)
    tags = set(card.tags)
    scored: list[tuple[float, str]] = []
    seen = {target}
    for other in pool:
        if other.id == card.id:
            continue
        key = normalize(other.definition)
        if not key or key in seen:
            continue
        seen.add(key)
        score = abs(_words(other.definition) - _words(card.definition))
        score -= 3 * len(tags & set(other.tags))
        scored.append((score + rng.random() * 2, other.definition))
    scored.sort(key=lambda t: t[0])
    best = [d for _, d in scored[:k + 2]]  # a little slack so quizzes vary
    rng.shuffle(best)
    return best[:k]


def make_mc(card: StudyCard, pool: Sequence[StudyCard], rng: random.Random) -> Question | None:
    wrong = pick_distractors(card, pool, MC_OPTIONS - 1, rng)
    if len(wrong) < MC_OPTIONS - 1:
        return None
    options = [card.definition, *wrong]
    rng.shuffle(options)
    return Question("mc", card.id, card.term, card.definition, tuple(options),
                    options.index(card.definition), context="Pick the definition")


def make_tf(card: StudyCard, pool: Sequence[StudyCard], rng: random.Random) -> Question | None:
    others = [c.definition for c in pool
              if c.id != card.id and normalize(c.definition) != normalize(card.definition)]
    if not others:
        return None
    truth = rng.random() < 0.5
    shown = card.definition if truth else rng.choice(others)
    return Question("tf", card.id, card.term, "True" if truth else "False", ("True", "False"),
                    0 if truth else 1, context="True or false?", statement=shown,
                    back=card.definition)


_TOKEN = re.compile(r"[^\W_][\w'’-]*", re.UNICODE)


def key_word(definition: str, term: str, rng: random.Random) -> tuple[int, int] | None:
    """(start, end) of the word to blank: the longest / most specific non-stopword (capitals
    mid-sentence and numbers score higher; words of the term itself are skipped)."""
    term_words = {normalize(w) for w in term.split()}
    best: list[tuple[float, int, int]] = []
    for idx, m in enumerate(_TOKEN.finditer(definition)):
        w = m.group(0).strip("'’-")
        key = normalize(w)
        if not key or key in STOPWORDS or key in term_words:
            continue
        if len(key) < 3 and not key.isdigit():
            continue
        score = float(len(key))
        if idx > 0 and w[:1].isupper():
            score += 3
        if any(ch.isdigit() for ch in w):
            score += 2
        start = m.start() + m.group(0).find(w)
        best.append((score, start, start + len(w)))
    if not best:
        return None
    top = max(s for s, _, _ in best)
    _, a, b = rng.choice([t for t in best if t[0] == top])
    return a, b


def make_fill(card: StudyCard, rng: random.Random) -> Question | None:
    if _words(card.definition) < 3:
        return None
    span = key_word(card.definition, card.term, rng)
    if span is None:
        return None
    a, b = span
    prompt = card.definition[:a] + BLANK + card.definition[b:]
    return Question("fill", card.id, prompt, card.definition[a:b], context=card.term,
                    back=card.definition)


def make_type(card: StudyCard) -> Question:
    """Short definitions (<= 4 words, e.g. Q/A cards) are typed from the term; otherwise
    the term is typed from its definition."""
    if _words(card.definition) <= 4:
        return Question("type", card.id, card.term, card.definition, context="Type the answer",
                        back=card.definition)
    return Question("type", card.id, card.definition, card.term, context="Type the term",
                    back=card.term)


def make_flip(card: StudyCard) -> Question:
    return Question("flip", card.id, card.term, card.definition, back=card.definition,
                    context=card.hint)


def make_question(card: StudyCard, kind: str, pool: Sequence[StudyCard],
                  rng: random.Random) -> Question:
    """One question; falls back mc -> tf -> type and fill -> type when the deck or the card
    can't support the kind."""
    if kind == "flip":
        return make_flip(card)
    if kind == "mc" and (q := make_mc(card, pool, rng)):
        return q
    if kind in ("mc", "tf") and (q := make_tf(card, pool, rng)):
        return q
    if kind == "fill" and (q := make_fill(card, rng)):
        return q
    return make_type(card)


def is_due(card: StudyCard, today: date) -> bool:
    return not card.due or card.due <= today.isoformat()


def study_order(cards: Sequence[StudyCard], today: date, rng: random.Random) -> list[StudyCard]:
    """Due cards first (lowest box, then oldest due), then the rest by box; ties shuffled."""
    keyed = [(not is_due(c, today), c.box, c.due or "", rng.random(), c) for c in cards]
    keyed.sort(key=lambda t: t[:4])
    return [t[4] for t in keyed]


def build_quiz(cards: Sequence[StudyCard], kinds: Sequence[str], count: int, today: date,
               rng: random.Random | None = None) -> list[Question]:
    """`count` questions (at most one per card), due cards first, kinds mixed evenly in a
    shuffled order. kinds: any of QUESTION_KINDS (empty = QUIZ_KINDS)."""
    rng = rng or random.Random()
    kinds = [k for k in kinds if k in QUESTION_KINDS] or list(QUIZ_KINDS)
    chosen = study_order(cards, today, rng)[:max(0, min(int(count), len(cards)))]
    rng.shuffle(chosen)
    plan = [kinds[i % len(kinds)] for i in range(len(chosen))]
    rng.shuffle(plan)
    return [make_question(c, k, cards, rng) for c, k in zip(chosen, plan, strict=True)]


def grade(q: Question, response: Any) -> Grade:
    """mc / tf: the picked option index; fill / type: the typed text; flip: True = knew it,
    or a rating from RATINGS ("again" = didn't know)."""
    if q.kind == "flip":
        if isinstance(response, str):
            return Grade(response != "again", expected=q.answer)
        return Grade(bool(response), expected=q.answer)
    if q.kind in ("mc", "tf"):
        try:
            ok = int(response) == q.correct
        except (TypeError, ValueError):
            ok = False
        return Grade(ok, expected=q.answer)
    verdict = check_text(str(response or ""), q.answer)
    return Grade(verdict != "wrong", verdict == "close", q.answer)


# --- a study run (exam / learn / flip) --------------------------------------------------------------
LEARN_GAP = 3  # a missed question comes back after this many others (learn mode)


class StudyRun:
    """One session. Exam: each question once. Learn: a missed card is asked again a few
    questions later until it is answered right. A time limit (seconds, 0 = none) ends it
    with `expire()`; unanswered cards then count as missed. Only the FIRST answer per card
    counts for the score and spaced repetition."""

    def __init__(self, questions: Sequence[Question], *, learn: bool = False,
                 time_limit_s: int = 0) -> None:
        self.queue: list[Question] = list(questions)
        self.cards: list[str] = list(dict.fromkeys(q.card_id for q in questions))
        self.learn = learn
        self.time_limit_s = max(0, int(time_limit_s))
        self.pos = 0
        self.first: dict[str, bool] = {}  # card id -> first answer right?
        self.mastered: set[str] = set()  # learn: answered right at least once
        self.answers: list[tuple[Question, Grade]] = []
        self.ratings: dict[str, str] = {}  # flip: card id -> first self-rating
        self.timed_out = False

    @property
    def current(self) -> Question | None:
        return None if self.finished else self.queue[self.pos]

    @property
    def finished(self) -> bool:
        return self.timed_out or self.pos >= len(self.queue)

    @property
    def total(self) -> int:
        return len(self.cards)

    @property
    def progress(self) -> float:
        """0..1: cards answered (exam) or cards answered right (learn)."""
        if not self.cards:
            return 1.0
        done = len(self.mastered) if self.learn else len(self.first)
        return done / len(self.cards)

    def answer(self, response: Any) -> Grade:
        q = self.current
        if q is None:
            raise RuntimeError("the run is over")
        g = grade(q, response)
        self.answers.append((q, g))
        self.first.setdefault(q.card_id, g.correct)
        if q.kind == "flip" and response in RATINGS:
            self.ratings.setdefault(q.card_id, response)
        if g.correct:
            self.mastered.add(q.card_id)
        elif self.learn:
            at = min(len(self.queue), self.pos + 1 + LEARN_GAP)
            self.queue.insert(at, q)
        self.pos += 1
        return g

    def expire(self) -> None:
        """Time is up: every card not answered yet counts as missed."""
        for cid in self.cards:
            self.first.setdefault(cid, False)
        self.timed_out = True

    def results(self) -> list[tuple[str, bool]]:
        """(card id, first answer right) for every card answered (or expired)."""
        return [(cid, self.first[cid]) for cid in self.cards if cid in self.first]

    def score(self) -> tuple[int, int]:
        r = self.results()
        return sum(ok for _, ok in r), len(r)

    def missed(self) -> list[str]:
        return [cid for cid, ok in self.results() if not ok]


# --- spaced repetition + XP ----------------------------------------------------------------------
RATINGS = ("again", "hard", "good", "easy")  # flip-card self-rating, worst first
CARD_STATES = ("new", "learning", "reviewing", "confident")
STATE_LABELS = {"new": "New", "learning": "Learning", "reviewing": "Reviewing",
                "confident": "Confident"}
DECK_CATEGORIES = ("course", "project", "skill", "path")
DEFAULT_DAILY_LIMIT = 20
MAX_DAILY_LIMIT = 500
WEAK_ACCURACY = 0.6  # a seen card right less often than this (or in box 0-1) is weak


def review(card: StudyCard, correct: bool, today: date, rating: str | None = None) -> None:
    """Leitner step. Quiz answers: right -> one box up, wrong -> box 0 (due today, so it
    leads the next session). A flip-card rating refines it: again = wrong, hard = stay in
    the box (at least 1) and come back tomorrow, good = one box up, easy = two boxes up.
    The card is due again after BOX_DAYS[box] days."""
    if rating not in RATINGS:
        rating = "good" if correct else "again"
    if rating == "again":
        card.box = 0
        days = 0
    elif rating == "hard":
        card.box = max(1, card.box)
        days = 1
    else:
        card.box = min(card.box + (2 if rating == "easy" else 1), MAX_BOX)
        days = BOX_DAYS[card.box]
    card.due = (today + timedelta(days=days)).isoformat()
    card.seen += 1
    card.right += int(rating != "again")
    card.last_seen = today.isoformat()


def card_state(card: StudyCard) -> str:
    """new (never answered) -> learning (box 0-1) -> reviewing (box 2-3) -> confident."""
    if card.seen == 0:
        return "new"
    if card.box >= MASTERED_BOX:
        return "confident"
    return "reviewing" if card.box >= 2 else "learning"


def deck_progress(deck: StudyDeck) -> dict[str, int]:
    """Cards per state, in CARD_STATES order (for the deck progress bar)."""
    out = dict.fromkeys(CARD_STATES, 0)
    for c in deck.cards:
        out[card_state(c)] += 1
    return out


def accuracy(card: StudyCard) -> float | None:
    return card.right / card.seen if card.seen else None


def weak_cards(deck: StudyDeck) -> list[StudyCard]:
    """Seen cards that keep slipping (last answer missed = box 0, or under WEAK_ACCURACY
    right overall), weakest first."""
    weak = [c for c in deck.cards
            if c.seen and (c.box == 0 or (accuracy(c) or 0) < WEAK_ACCURACY)]
    return sorted(weak, key=lambda c: (accuracy(c) or 0, c.box, -c.seen))


def days_to_exam(deck: StudyDeck, today: date) -> int | None:
    """Days until the deck's exam (0 = today), None when there is no date or it has passed."""
    if not deck.exam_date:
        return None
    try:
        left = (date.fromisoformat(deck.exam_date) - today).days
    except ValueError:
        return None
    return left if left >= 0 else None


def study_xp(answered: int, nth_today: int, xp_today: int) -> int:
    """XP for one finished session: STUDY_XP_PER_CARD per card answered, capped per
    session, scaled down for repeat sessions on the same deck today (nth_today is 0 for
    the first), and capped per day. 0 below STUDY_MIN_CARDS."""
    if answered < STUDY_MIN_CARDS:
        return 0
    mult = STUDY_REPEAT_MULT[nth_today] if 0 <= nth_today < len(STUDY_REPEAT_MULT) else 0.0
    xp = int(min(answered * STUDY_XP_PER_CARD, STUDY_SESSION_XP_CAP) * mult)
    return max(0, min(xp, STUDY_DAILY_XP_CAP - xp_today))


def is_strong(right: int, total: int) -> bool:
    return total >= STUDY_MIN_CARDS and right / total >= STRONG_SCORE


@dataclass(frozen=True)
class DeckStats:
    total: int
    due: int  # due now (no daily limit applied)
    new: int
    mastered: int  # = confident


def deck_stats(deck: StudyDeck, today: date) -> DeckStats:
    return DeckStats(len(deck.cards), sum(is_due(c, today) for c in deck.cards),
                     sum(c.seen == 0 for c in deck.cards),
                     sum(c.box >= MASTERED_BOX for c in deck.cards))


def _merge(a: Completion, b: Completion) -> Completion:
    return Completion(a.xp + b.xp, a.coins + b.coins, a.levels_gained + b.levels_gained,
                      a.path_id or b.path_id, a.path_levels_gained + b.path_levels_gained,
                      a.capped or b.capped, ref_id=a.ref_id)


class StudyMixin:
    """Game methods for Study decks. Relies on Game's data/_new_id/_award/_find and
    quest/complete_quest/add_quest."""

    data: SaveData

    if TYPE_CHECKING:  # provided by Game
        def _new_id(self, prefix: str) -> str: ...
        def _award(self, xp: int, coins: int, path_id: str, today: date) -> Completion: ...
        def _find(self, items: list, item_id: str) -> Any: ...
        def quest(self, quest_id: str) -> Quest: ...
        def complete_quest(self, quest_id: str, today: date) -> Completion: ...
        def add_quest(self, title: str, path_id: str, kind: str = ..., difficulty: int = ...,
                      note: str = ..., today: date | None = ...) -> Quest: ...

    # decks
    @property
    def decks(self) -> list[StudyDeck]:
        return self.data.decks

    def deck(self, deck_id: str) -> StudyDeck:
        return self._find(self.data.decks, deck_id)

    def add_deck(self, title: str, today: date, subject: str = "", path_id: str = STUDY_PATH,
                 color: str = "", category: str = "course") -> StudyDeck:
        title = " ".join(str(title).split())
        if not title:
            raise ValueError("give the deck a name")
        if category not in DECK_CATEGORIES:
            raise ValueError(f"category must be one of {DECK_CATEGORIES}")
        color = color or DECK_COLORS[len(self.data.decks) % len(DECK_COLORS)]
        deck = StudyDeck(self._new_id("sd"), title[:60], " ".join(subject.split())[:40],
                         path_id or STUDY_PATH, color, today.isoformat(), category=category)
        self.data.decks.append(deck)
        return deck

    def edit_deck(self, deck_id: str, *, title: str | None = None, subject: str | None = None,
                  color: str | None = None, path_id: str | None = None,
                  category: str | None = None, daily_limit: int | None = None,
                  exam_date: date | str | None = None) -> StudyDeck:
        """exam_date: a date, "" to clear, None to keep. daily_limit: 0 = the global one."""
        d = self.deck(deck_id)
        if title is not None:
            title = " ".join(title.split())
            if not title:
                raise ValueError("give the deck a name")
            d.title = title[:60]
        if subject is not None:
            d.subject = " ".join(subject.split())[:40]
        if category is not None:
            if category not in DECK_CATEGORIES:
                raise ValueError(f"category must be one of {DECK_CATEGORIES}")
            d.category = category
        if daily_limit is not None:
            d.daily_limit = max(0, min(int(daily_limit), MAX_DAILY_LIMIT))
        if exam_date is not None:
            d.exam_date = exam_date.isoformat() if isinstance(exam_date, date) else (
                date.fromisoformat(exam_date).isoformat() if exam_date else "")
        if color:
            d.color = color
        if path_id:
            d.path_id = path_id
        return d

    def delete_deck(self, deck_id: str) -> None:
        """Removes the deck and its cards; past sessions (and their XP) stay. A linked quest
        stays a normal quest."""
        self.data.decks.remove(self.deck(deck_id))

    def set_study_limit(self, daily_limit: int) -> None:
        """Global due reviews per deck per day (0 = no limit)."""
        self.data.study_settings.daily_limit = max(0, min(int(daily_limit), MAX_DAILY_LIMIT))

    def deck_limit(self, deck: StudyDeck) -> int:
        """Due reviews per day for this deck (0 = no limit)."""
        return deck.daily_limit or self.data.study_settings.daily_limit

    def due_today(self, deck_id: str, today: date) -> list[StudyCard]:
        """The due cards to review today, most urgent first, cut to what is left of the
        deck's daily limit after today's sessions."""
        deck = self.deck(deck_id)
        due = [c for c in deck.cards if is_due(c, today)]
        due.sort(key=lambda c: (c.box, c.seen == 0, c.due or ""))  # misses before new
        limit = self.deck_limit(deck)
        if not limit:
            return due
        done = sum(s.total for s in self.study_sessions(today, deck_id))
        return due[:max(0, limit - done)]

    # linked quest + exam
    def link_quest(self, deck_id: str, today: date) -> Quest:
        """Create a daily Path quest 'Review <deck> deck' that a finished session on this deck
        completes (or return the one already linked)."""
        d = self.deck(deck_id)
        q = self.linked_quest(deck_id)
        if q is not None:
            return q
        q = self.add_quest(f"Review {d.title} deck", d.path_id or STUDY_PATH, "daily", 1,
                           "Finish a study session on this deck.", today)
        d.quest_id = q.id
        return q

    def unlink_quest(self, deck_id: str) -> None:
        self.deck(deck_id).quest_id = ""

    def linked_quest(self, deck_id: str) -> Quest | None:
        d = self.deck(deck_id)
        if not d.quest_id:
            return None
        try:
            return self.quest(d.quest_id)
        except KeyError:
            return None

    # cards
    def card(self, deck_id: str, card_id: str) -> StudyCard:
        return self._find(self.deck(deck_id).cards, card_id)

    @staticmethod
    def _clean_card(term: str, definition: str) -> tuple[str, str]:
        term, definition = " ".join(str(term).split()), str(definition).strip()
        if not term or not definition:
            raise ValueError("a card needs a term and a definition")
        return term[:MAX_TERM_CHARS], definition[:MAX_DEF_CHARS]

    def add_card(self, deck_id: str, term: str, definition: str, *, hint: str = "",
                 example: str = "", tags: Iterable[str] = ()) -> StudyCard:
        d = self.deck(deck_id)
        term, definition = self._clean_card(term, definition)
        c = StudyCard(self._new_id("sc"), term, definition, hint.strip(), example.strip(),
                      [t.strip() for t in tags if t.strip()])
        d.cards.append(c)
        return c

    def add_cards(self, deck_id: str, drafts: Iterable[Draft]) -> list[StudyCard]:
        """Save the drafts the player accepted (skips any with an empty side)."""
        out = []
        for dr in drafts:
            if dr.term.strip() and dr.definition.strip():
                out.append(self.add_card(deck_id, dr.term, dr.definition))
        return out

    def edit_card(self, deck_id: str, card_id: str, *, term: str | None = None,
                  definition: str | None = None, hint: str | None = None,
                  example: str | None = None, tags: Iterable[str] | None = None) -> StudyCard:
        c = self.card(deck_id, card_id)
        t, dfn = self._clean_card(c.term if term is None else term,
                                  c.definition if definition is None else definition)
        c.term, c.definition = t, dfn
        if hint is not None:
            c.hint = hint.strip()
        if example is not None:
            c.example = example.strip()
        if tags is not None:
            c.tags = [x.strip() for x in tags if x.strip()]
        return c

    def delete_card(self, deck_id: str, card_id: str) -> None:
        d = self.deck(deck_id)
        d.cards.remove(self.card(deck_id, card_id))

    # sessions
    def study_sessions(self, day: date | None = None,
                       deck_id: str | None = None) -> list[StudySession]:
        return [s for s in self.data.study_sessions
                if (day is None or s.day == day.isoformat())
                and (deck_id is None or s.deck_id == deck_id)]

    def finish_study(self, deck_id: str, mode: str, results: Sequence[tuple[str, bool]],
                     today: date, seconds: int = 0,
                     ratings: dict[str, str] | None = None) -> Completion:
        """Record a finished run: spaced repetition for every answered card (flip ratings
        refine it), a StudySession, capped XP/coins to the deck's Path, and the linked quest
        completed (normal quest reward, once per day). Call once per run (the run object is
        the guard). Completion.ref_id = the session id."""
        if mode not in STUDY_MODES:
            raise ValueError(f"mode must be one of {STUDY_MODES}")
        deck = self.deck(deck_id)
        ratings = ratings or {}
        by_id = {c.id: c for c in deck.cards}
        counted = [(cid, ok) for cid, ok in results if cid in by_id]
        for cid, ok in counted:
            review(by_id[cid], ok, today, ratings.get(cid))
        right = sum(ok for _, ok in counted)
        same_deck = self.study_sessions(today, deck_id)
        nth = sum(1 for s in same_deck if s.xp > 0)
        xp_today = sum(s.xp for s in self.study_sessions(today))
        coins_today = sum(s.coins for s in self.study_sessions(today))
        xp = study_xp(len(counted), nth, xp_today)
        coins = (min(STUDY_COINS, max(0, STUDY_DAILY_COIN_CAP - coins_today))
                 if xp and nth == 0 else 0)
        c = self._award(xp, coins, deck.path_id or STUDY_PATH, today)
        s = StudySession(self._new_id("ss"), deck_id, today.isoformat(), mode, len(counted),
                         right, max(0, int(seconds)), c.xp, c.coins)
        self.data.study_sessions.append(s)
        c.ref_id = s.id
        if counted and self.linked_quest(deck_id) is not None:
            c = _merge(c, self.complete_quest(deck.quest_id, today))
        return c
