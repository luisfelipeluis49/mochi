"""Run:  .venv/bin/python -m unittest discover tests"""
import unittest

from mochi_device.backends import TAG, _moved
from mochi_device.device import Device, reachable


class FakeMixer(Device):
    def __init__(self, switch: bool = True):
        super().__init__({"device": "plughw:CARD=M1A,DEV=0", "min_volume": 20})
        self.level = 100
        self.switch = switch  # does this mixer have a mute switch?
        self.muted = False

    def _amixer(self, *args):
        if args[0] == "sset":
            for arg in args[2:]:
                if arg in ("mute", "unmute"):
                    self.muted = self.switch and arg == "mute"
                else:
                    self.level = int(arg.rstrip("%"))
        state = f" [{'off' if self.muted else 'on'}]" if self.switch else ""
        return f"  Mono: Playback {self.level} [{self.level}%] [0.39dB]{state}"


class DeviceTest(unittest.TestCase):
    def test_card_from_device_name(self):
        self.assertEqual(FakeMixer().card, "M1A")

    def test_volume_stays_within_limits(self):
        d = FakeMixer()
        self.assertEqual(d.set_volume(60), 60)
        self.assertEqual(d.set_volume(0), 20)      # never silent
        self.assertEqual(d.set_volume(250), 100)

    def test_mute_keeps_the_level(self):
        d = FakeMixer()
        d.set_volume(60)
        d.set_muted(True)
        self.assertTrue(d.muted)
        d.set_muted(False)
        self.assertEqual((d.muted, d.volume()), (False, 60))

    def test_mute_on_a_mixer_without_a_switch(self):
        d = FakeMixer(switch=False)
        d.set_volume(60)
        d.set_muted(True)
        d.set_muted(True)  # twice must not forget the level
        self.assertEqual(d.volume(), 0)
        d.set_muted(False)
        self.assertEqual(d.volume(), 60)

    def test_a_volume_command_does_not_unmute_a_muted_speaker(self):
        d = FakeMixer()
        d.set_volume(60)
        d.set_muted(True)
        d.set_volume(40)                      # the backend still wants it quieter
        self.assertTrue(d.muted)              # ...but Mochi stays silent
        d.set_muted(False)
        self.assertEqual((d.muted, d.volume()), (False, 40))  # and the new level is applied

    def test_a_volume_command_on_a_muted_mixer_without_a_switch(self):
        d = FakeMixer(switch=False)
        d.set_volume(60)
        d.set_muted(True)
        d.set_volume(40)
        self.assertEqual(d.volume(), 0)       # still silent
        d.set_muted(False)
        self.assertEqual(d.volume(), 40)

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


class ConfigTest(unittest.TestCase):
    def test_this_devices_own_choices_go_on_top(self):
        import tempfile
        from pathlib import Path

        from mochi_device import config

        with tempfile.TemporaryDirectory() as d:
            shared, local = Path(d) / "mochi.toml", Path(d) / "mochi.local.toml"
            shared.write_text('[backend]\nkind = "test_agent"\ndevice_id = "home_pi_01"\n')
            self.assertEqual(config.load_with_local(shared, local)["backend"]["kind"], "test_agent")
            local.write_text('[backend]\nkind = "mochi_backend"\n[face]\nenabled = false\n')
            cfg = config.load_with_local(shared, local)
            self.assertEqual(cfg["backend"], {"kind": "mochi_backend", "device_id": "home_pi_01"})
            self.assertEqual(cfg["face"], {"enabled": False})
            self.assertEqual(config.load(shared)["backend"]["kind"], "test_agent")  # the file itself


class ConnectionTest(unittest.TestCase):
    """Does Mochi have a connection? A look opens a connection to a well-known address and closes it."""

    def test_one_address_that_answers_is_enough(self):
        tried, closed = [], []

        def connect(address, timeout):
            tried.append(address)
            if address[0] == "1.1.1.1":
                raise OSError("network is unreachable")
            return type("Opened", (), {"close": lambda self: closed.append(address)})()
        self.assertTrue(reachable(("1.1.1.1:443", "8.8.8.8:53"), 1, connect))
        self.assertEqual(tried, [("1.1.1.1", 443), ("8.8.8.8", 53)])
        self.assertEqual(closed, [("8.8.8.8", 53)])            # opened and closed: nothing is sent

    def test_no_address_answers_or_none_is_given(self):
        def nothing(address, timeout):
            raise OSError("timed out")
        self.assertFalse(reachable(("1.1.1.1:443", "8.8.8.8:53"), 1, nothing))
        self.assertFalse(reachable(("not an address",), 1, nothing))
        self.assertFalse(reachable((), 1, nothing))


if __name__ == "__main__":
    unittest.main()
