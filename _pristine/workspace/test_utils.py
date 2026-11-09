from utils import slugify, word_count, top_words


def test_slugify_joins_with_dashes():
    assert slugify("hello world") == "hello-world"


def test_slugify_lowercases():
    assert slugify("Hello World!") == "hello-world"


def test_word_count():
    assert word_count("one two  three") == 3


def test_top_words():
    assert top_words("a b a c b a", n=2) == ["a", "b"]
