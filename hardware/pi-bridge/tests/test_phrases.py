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
