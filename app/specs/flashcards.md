We're going to build flashcards into this application for people to do their language study. The most basic requirement is that we're going to use spaced repetition. You can look up how this usually works, which will be better than my imperfect explanation.

So we'll build slide decks and show people cards based on a spaced repetition algorithm. Things they'll control:
* whether they have one set of flash cards across all text, or individual sets per text. Ultimately we'll want to let them switch easily, but that's unnecessary for the first pass
* they'll control whether they only see cards for words in the "other" language, or whether they should see both sides
* they'll control how many terms are added per day, and what the maximum number of cards is per day (maybe 10 & 100 as defaults?)
* they'll control whether words are added from the beginning of a text, based on what's most common in the text, or a balanced attempt at the two, which favors common over uncommon words yet also partially works from beginning to end of the text
* they'll choose what text(s) to build their flash cards from. E.g., the Odyssey, or Book one of the Odyssey, etc.
* when you show a card, they'll say whether they got it right or not (later we might add typing in answers and more formally "testing" them. We'll see), which will cause you to set when it next gets repeated
* at a future point, they'll probably want to control what words not to show - e.g., proper names, or words which occur less than 3 times or 10 times in the text, etc.