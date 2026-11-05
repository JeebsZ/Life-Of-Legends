# Content sources (v1.3)

Free, legal learning resources referenced in `src/lol/core/catalog_extra.py`. Notes use the form
`Resource: <Title> — <URL>`. All URLs were opened and checked on **2026-11-04**. No affiliate links.

"Board" = an `EXTRA_QUEST_BOARD` quest. Chain ids are `EXTRA_SIDE_QUESTS` ids (`-r2`/`-r3` = follow-ups).

## Public-domain books (Project Gutenberg / Standard Ebooks)
Pre-1930 works, public domain in the US; free to read and download. Standard Ebooks releases are
public-domain texts with CC0 dedications for their own edits.

| Title | URL | Used by |
|---|---|---|
| The Boston Cooking-School Cook Book (Fannie Farmer) | https://www.gutenberg.org/ebooks/65061 | Board "Pick a recipe from a classic cookbook"; `soups-and-stews-r2` |
| The Book of Household Management (Mrs. Beeton) | https://www.gutenberg.org/ebooks/10136 | `kitchen-hygiene-r3`; `household-routines-r2` |
| Boy Scouts Handbook, 1911 | https://www.gutenberg.org/ebooks/29558 | `outdoor-readiness` |
| The Elements of Drawing (John Ruskin) | https://www.gutenberg.org/ebooks/30325 | Board "Draw one object from life"; `drawing-from-life` |
| Textiles and Clothing (Kate Heintz Watson) | https://www.gutenberg.org/ebooks/21534 | Board "Mend a small tear in clothing"; `mending-and-sewing-r2` |
| Handbook of Nature-Study (Anna Botsford Comstock) | https://www.gutenberg.org/ebooks/78142 | Board "Start a nature journal page"; `nature-journaling`; `drawing-from-life-r2` |
| Walden (Henry David Thoreau, Standard Ebooks) | https://standardebooks.org/ebooks/henry-david-thoreau/walden | Board "Read a page of Walden outside" |
| Autobiography of Benjamin Franklin | https://www.gutenberg.org/ebooks/20203 | `saving-habits-r2` |
| The Art of Money Getting (P. T. Barnum) | https://www.gutenberg.org/ebooks/8581 | `saving-habits-r3` (read as a historical classic, not advice) |
| Meditations (Marcus Aurelius, tr. George Long, Standard Ebooks) | https://standardebooks.org/ebooks/marcus-aurelius/meditations/george-long | Board "Read one passage of Meditations"; `stoic-reflection` |
| The Enchiridion (Epictetus) | https://www.gutenberg.org/ebooks/45109 | `stoic-reflection-r2` |
| As a Man Thinketh (James Allen) | https://www.gutenberg.org/ebooks/4507 | `stoic-reflection-r3` |
| How to Live on 24 Hours a Day (Arnold Bennett) | https://www.gutenberg.org/ebooks/2274 | `rest-routine-r2` |

## OpenStax textbooks
Free to read online and as PDF; openly licensed under Creative Commons (OpenStax's CMS lists
CC BY-NC-SA for these titles; check each book page for the exact license before quoting text).
Book slugs were confirmed via the OpenStax CMS API.

| Title | URL | Used by |
|---|---|---|
| Psychology 2e | https://openstax.org/details/books/psychology-2e | Board "Read one section of a free textbook"; `psychology-basics`; `psychology-basics-r2` |
| Lifespan Development | https://openstax.org/details/books/lifespan-development | `psychology-basics-r3` |
| College Success | https://openstax.org/details/books/college-success | Board "Plan your study week"; `study-skills` |
| Introduction to Python Programming | https://openstax.org/details/books/introduction-python-programming | `python-starter` |
| Concepts of Biology | https://openstax.org/details/books/concepts-biology | `nature-journaling-r2` |
| Principles of Finance | https://openstax.org/details/books/principles-finance | `money-basics-r2` |
| Principles of Economics 3e | https://openstax.org/details/books/principles-economics-3e | `money-basics-r3` |

Also verified but not used in catalog_extra (the existing Marketing chain may use it):
Principles of Marketing — https://openstax.org/details/books/principles-marketing; Entrepreneurship —
https://openstax.org/details/books/entrepreneurship.

## Free courses
| Title | URL | Why free | Used by |
|---|---|---|---|
| CS50x (Harvard) | https://cs50.harvard.edu/x/ | Free course materials and lectures (certificate via edX optional/paid) | Board "Watch part of a free CS50 lecture"; `python-starter-r3` |
| freeCodeCamp | https://www.freecodecamp.org/learn/ | Nonprofit, free curriculum | Board "Complete one freeCodeCamp lesson"; `python-starter-r2` |
| MIT OpenCourseWare | https://ocw.mit.edu/ | Free course materials (CC BY-NC-SA) | Board "Browse a free university course"; `study-skills-r3` |
| Khan Academy — Financial Literacy | https://www.khanacademy.org/college-careers-more/financial-literacy | Nonprofit, free course (US-focused; concepts apply broadly) | Board "Learn one money term"; `money-basics` |

## Government guides
US federal works are generally public domain and free to read.

| Title | URL | Used by |
|---|---|---|
| Move Your Way (U.S. ODPHP, health.gov) | https://odphp.health.gov/moveyourway | Board "Explore ideas for moving more"; `core-strength-r3` |
| About Handwashing (CDC) | https://www.cdc.gov/clean-hands/about/index.html | Board "Wash your hands the full 20 seconds"; `daily-hygiene`; `kitchen-hygiene` |
| About Oral Health (CDC) | https://www.cdc.gov/oral-health/about/index.html | `daily-hygiene-r2` |
| How Sleep Works (NHLBI, NIH) | https://www.nhlbi.nih.gov/health/sleep | `rest-routine` |
| Consumer Resources (U.S. CFPB) | https://www.consumerfinance.gov/consumer-tools/ | `money-basics-r2` |

## Checked and not used
- FoodSafety.gov safe minimum temperatures chart and USDA FSIS temperature chart: both returned
  HTTP 403 to automated checks, so they could not be verified and were left out.
- CDC "Preventing Oral Diseases" page (https://www.cdc.gov/oral-health/prevention/index.html) is
  community-level, so the "About Oral Health" page is used instead.
- Internet Archive (https://archive.org/details/texts) is reachable but no specific title is cited.
