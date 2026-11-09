# Rubric: explain_trace

Each line starting with "- " is one criterion the judge grades pass/fail.
Lines containing TODO are skipped. Fill them in live with your guest.

A criterion written as `max_words: N` or `max_lines: N` is checked by code, not by the
judge. Models are bad at counting; don't ask them to. (To watch the judge guess, replace
the last line with "Under 150 words" and run grade --twice.)

- Correctly identifies the cause: the user dict has no "shipping_address" key when build_order runs
- Points to a concrete first place to look (orders.py line 58, or where the user dict is built, or whether the key is optional)
- Pitched at a junior engineer: no unexplained jargon, no condescension, assumes they know Python basics
- TODO: add a criterion your guest cares about (e.g. suggests a defensive fix like .get(), mentions adding a test)
- max_words: 150
