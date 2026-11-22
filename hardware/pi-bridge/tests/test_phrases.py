"""Phrase matching on phone strings as the recogniser writes them (taken from real runs).
Run:  .venv/bin/python -m unittest discover tests
"""
import unittest

from mochi_device.phrases import PhraseMatcher, fold

GROUPS = {"wake": ["oi mochi", "olá mochi", "hi mochi", "hey mochi", "hello mochi"],
          "goodbye": ["tchau mochi", "bye mochi", "goodbye mochi"]}


class PhraseMatcherTest(unittest.TestCase):
    def setUp(self):
        self.m = PhraseMatcher(GROUPS, ignore=["mochila"])

    def group(self, phones, **kw):
        hit = self.m.match(phones, **kw)
        return hit.group if hit else None

    def test_fold(self):
        self.assertEqual(fold("haɪmoʊtʃi"), "haimoutSi")
        self.assertEqual(fold("ojmɔtɕi"), "oimotSi")

    def test_wake_english_and_portuguese(self):
        for heard in ("haɪmoʊtʃi", "heɪmoʊtʃi", "emoʊtʃi", "aɪmotʃi", "aloʊmoʊtʃi",      # hi / hey / hello
                      "ojmɔtɕi", "wɔimwɔtɕi", "olamotʃi", "ajmwotɕi", "ojmoatʃi",       # oi / olá / "rai"
                      "ojmoʃi", "ainmutɕi", "ojmɔtʃ"):                                   # moshi, stray n, lost final i
            self.assertEqual(self.group(heard), "wake", heard)

    def test_the_greeting_says_which_language_mochi_was_called_in(self):
        """The phrase reported decides the language Mochi greets in. A Brazilian "oi" is heard with a
        rounded start and an open end, the same sounds as "hey" and "hi" after it: on the test clips
        four in ten Portuguese greetings were answered in English before these were told apart."""
        def cue(heard):
            return self.m.match(heard).phrase.split()[0]
        for heard in ("ojmɔtɕi", "ueimuotʃi", "uaimuotʃi", "uoueimuoʃi", "hueimuotʃi", "tueimuoʃi",   # oi
                      "olamotʃi", "poamotʃi", "tuamuotʃi"):                                             # olá
            self.assertIn(cue(heard), ("oi", "ola"), heard)
        for heard in ("haɪmoʊtʃi", "heɪmoʊtʃi", "emoʊtʃi", "aɪmotʃi", "heloumoutʃi", "əloumoutʃi"):
            self.assertIn(cue(heard), ("hi", "hey", "hello"), heard)

    def test_you_like_mochi_is_not_ola_mochi(self):
        self.assertIsNone(self.group("duiulaikmoutʃiaizkrim"))      # "Do you like Mochi ice cream?"

    def test_goodbye(self):
        for heard in ("baɪmoʊtʃi", "gʊdbaɪmoʊtʃi", "tʃaumotʃi", "ʃaumuatʃi", "ɕianmuotɕi", "tabõtʃaumɔtʃi"):
            self.assertEqual(self.group(heard), "goodbye", heard)

    def test_opens_a_sentence(self):
        self.assertEqual(self.group("aɪmoʊtʃiwʌtsðəwədfɔɹkju"), "wake")       # hi mochi, what's the word for queue
        self.assertEqual(self.group("ojmotʃikomosidʒisfilaeminglejs"), "wake")  # oi mochi, como se diz fila...

    def test_not_mochi(self):
        for heard in ("boanojtʃi",              # boa noite
                      "haʊmʌtʃɪzɪt",            # how much is it
                      "amoʃilaeminja",          # a mochila é minha
                      "ojmujtuobrigadu",        # oi, muito obrigado
                      "soʊmʌtʃiziɚ",            # so much easier
                      "antʃimotʃinentraron",    # ...antimotim entraram
                      "eukomimotʃiontẽj",        # eu comi mochi ontem: the name, but nobody is calling it
                      "eukomimotʃi",            # ...also when it ends the sentence
                      "komekipamentoantʃimotʃi",  # ...equipamento antimotim: neither "oi" nor "tchau"
                      "tudubẽj", ""):
            self.assertIsNone(self.group(heard), heard)

    def test_still_talking(self):
        # "a mochi-" may yet become "a mochila": no decision until more is heard
        self.assertIsNone(self.group("amoʃi", final=False))
        self.assertIsNone(self.group("ojmotʃi", final=False))
        self.assertIsNone(self.group("amoʃiui", final=False))   # ...and its "l" is not always heard at once
        self.assertEqual(self.group("ojmotʃikomo", final=False), "wake")

    def test_custom_sound(self):
        m = PhraseMatcher(GROUPS, sounds={"mochi": ["motSi", "moti"]})  # European Portuguese "móti"
        self.assertEqual(m.match("ɔjmɔti").group, "wake")
        self.assertIsNone(self.m.match("ɔjmɔti"))


if __name__ == "__main__":
    unittest.main()


class StartPhrasesTest(unittest.TestCase):
    """A phrase without the name ("vamos papear" / "let's chat", the wake phrases of D-48) is found by
    its own last word. The shipped config wakes on greetings to Mochi again (D-65); these still work
    when someone configures them. Phone strings are what the recogniser wrote for spoken test clips
    (2026-11-22)."""

    def setUp(self):
        self.m = PhraseMatcher({"wake": ["vamos papear", "let's chat"],
                                "goodbye": ["tchau mochi", "bye mochi", "goodbye mochi"]}, ignore=["mochila"])

    def hit(self, phones, **kw):
        found = self.m.match(phones, **kw)
        return (found.group, found.phrase) if found else None

    def test_vamos_papear_as_it_is_really_heard(self):
        for heard in ("vamuspapea", "vamospapja", "vamospapeaɾ", "voʊmuspɑpjəɛ", "vomuʃpapjɛa",   # vamos papear
                      "vamupapea", "vomupɑpja", "zoʊmupɑpjɛ",                                      # vamo papear; a lost v
                      "bondʒivomuspapje", "bondiwvomospapɛa"):                                    # after "bom dia,"
            self.assertEqual(self.hit(heard), ("wake", "vamos papear"), heard)

    def test_lets_chat(self):
        for heard in ("lɛtstʃæt", "lɛtstʃɑt", "oʊkeɪlɛtstʃæt", "əkeɪlɛtstʃæt"):
            self.assertEqual(self.hit(heard), ("wake", "let s chat"), heard)

    def test_other_things_people_say_do_not_start_a_session(self):
        for heard in ("vamospasjaɾamaja", "vamosparaporaki", "vamospagaɾakoanta",   # passear, parar, pagar
                      "vamosprepararoɾelatɔrio", "upapɛwistanamɛzɐ",                 # preparar; o papel
                      "eogostodɛpapiakomɛlɐ", "aʒentʃifikowpapendateatadʒi",        # papear without "vamos"
                      "lɛtstʃɛkðənʌmbəz", "lɛtskætʃʌptumɑɹoʊ",                       # let's check, let's catch up
                      "wihædənaɪstʃætjɛstədeɪ",                                      # a chat, without "let's"
                      "ojmɔtɕi", "haɪmoʊtʃi"):                                       # greetings wake only when configured
            self.assertIsNone(self.hit(heard), heard)

    def test_a_look_alike_of_lets_chat_can_still_start_one(self):
        """Known and accepted for now: "chat" is four sounds, and "let's shut the door" is written
        with the same ones. "vamos papear" has no such neighbour on the test clips."""
        self.assertEqual(self.hit("lɛtsʃʌtðədɔɹ"), ("wake", "let s chat"))

    def test_goodbye_is_still_by_name(self):
        self.assertEqual(self.hit("tʃawmotʃi"), ("goodbye", "tchau mochi"))
        self.assertEqual(self.hit("baɪmoʊtʃi"), ("goodbye", "bye mochi"))

    def test_the_language_follows_the_phrase(self):
        self.assertEqual(self.m.match("vamuspapea").phrase.split()[0], "vamos")   # Portuguese greeting
        self.assertEqual(self.m.match("lɛtstʃæt").phrase.split()[0], "let")       # English greeting
