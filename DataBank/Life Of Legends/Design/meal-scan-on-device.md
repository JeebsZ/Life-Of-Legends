# Meal scan: on-device recognizer (4 Nov)

This is free, offline photo recognition, following the "free routes" decision in [[meal-scan-plan]].

- **Engine:** Google AIY *food_V1* TFLite classifier (Apache-2.0, 2,024 classes, 21 MB). It runs on the phone through our extension `extensions/flet_lumen_vision`, which uses `tflite_flutter`.
- **App side:** `ui/vision.py` provides `recognizer_for(page)`. On Android that returns `VisionRecognizer`; everywhere else it returns `ManualRecognizer`. `core/food_labels.py` holds the alias table that maps model labels to food ids, plus the filtering and merging, all with tests.
- **Filipino coverage:** the model knows 15 Filipino dishes: adobo, sinigang, kare-kare, bistek, kaldereta, menudo, halo-halo, champorado, bibingka, puto, kutsinta, suman, sapin-sapin, palitaw and sorbetes. It has no lumpia, pancit, sisig, lechon, tinola or longganisa. For those dishes the confirm card's search does the work.
- **Limits:** it names *one dish* per photo and guesses no portions. Grams come from you or the food's typical portion.
- **Accuracy test (8/10 bar):** take 10 real meals, one photo each, framed tight on the main dish. Count a meal as a hit when the right food is among the shown candidates. `VisionRecognizer.last_predictions` keeps the raw model output for tuning `MIN_CONFIDENCE`.
- **Status:** built but not yet verified on a device. It only runs in a `flet build apk` build.
