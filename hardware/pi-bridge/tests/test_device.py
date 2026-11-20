"""Run:  .venv/bin/python -m unittest discover tests"""
import unittest

from mochi_device.backends import TAG, _moved
from mochi_device.device import Device


class FakeMixer(Device):
    def __init__(self):
        super().__init__({"device": "plughw:CARD=M1A,DEV=0", "min_volume": 20})
        self.level = 100

    def _amixer(self, *args):
        if args[0] == "sset":
            self.level = int(args[2].rstrip("%"))
        return f"  Mono: Playback {self.level} [{self.level}%] [0.39dB] [on]"


class DeviceTest(unittest.TestCase):
    def test_card_from_device_name(self):
        self.assertEqual(FakeMixer().card, "M1A")

    def test_volume_stays_within_limits(self):
        d = FakeMixer()
        self.assertEqual(d.set_volume(60), 60)
        self.assertEqual(d.set_volume(0), 20)      # never silent
        self.assertEqual(d.set_volume(250), 100)

    def test_silent_commands_in_agent_reply(self):
        def tags(text):
            return [(m.group(1).lower(), m.group(2)) for m in TAG.finditer(text)]
        self.assertEqual(tags("[volume 60]Sure! Louder now."), [("volume", "60")])
        self.assertEqual(tags("[Volume: 40] Claro! Mais baixo agora."), [("volume", "40")])
        self.assertEqual(tags("[mood proud][show postpone] Isso! Now tell Ben."), [("mood", "proud"), ("show", "postpone")])
        self.assertEqual(tags("[mood cool][temp] Estou a 52 graus."), [("mood", "cool"), ("temp", "")])
        self.assertEqual(tags("[show guarda-chuva] Guarda-chuva!"), [("show", "guarda-chuva")])
        self.assertEqual(tags("Estou a 52 graus Celsius."), [])

    def test_when_the_agent_is_told_again(self):
        self.assertFalse(_moved((100, 53), (100, 52)))
        self.assertTrue(_moved((100, 54), (100, 52)))
        self.assertTrue(_moved((80, 52), (100, 52)))
        self.assertTrue(_moved((100, None), (100, 52)))
        self.assertFalse(_moved((100, None), (100, None)))


if __name__ == "__main__":
    unittest.main()
