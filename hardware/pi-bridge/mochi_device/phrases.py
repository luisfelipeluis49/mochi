"""Decides whether a string of recognised speech sounds is someone starting a session ("oi Mochi",
"hey Mochi") or leaving Mochi ("tchau Mochi").

The recogniser (see wakeword.py) writes what it hears as phones, not words, so "oi Mochi" arrives
as something like "ojmɔtɕi" and "tchau Mochi" as "tSaumɔtɕi" whichever language was spoken. Here
both the heard phones and the configured phrases are folded onto a small alphabet (fold), and a
phrase counts as heard when its anchor is found (weighted edit distance, so "moshi" and "motchi"
still count) with its cue words right in front of it. A phrase that has the name ("mochi") in it is
anchored on the name, wherever it stands; any other on its last word (a phrase without the name,
such as "vamos papear" or "let's chat", works when it is put in the config).

Folded alphabet: vowels a e i o u ə   consonants b d f g h k l m n p r s t v z, S (sh), Z (zh),
T / D (th).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_FOLD = {}
for _to, _from in {
    "a": "aɑæɐɶ", "e": "eɛøœɘɞ", "i": "iɪyɨjʏɥʝ", "o": "oɔɒɤɵ", "u": "uʊwɯʉɰʍ", "ə": "əɜʌ",
    "m": "mɱ", "n": "nɲŋɳɴ", "S": "ʃɕʂçɧ", "Z": "ʒʑʐ", "s": "s", "z": "z", "t": "tʈ", "d": "dɖɗ",
    "k": "kcq", "g": "gɡɟɠɢ", "p": "p", "b": "bɓ", "h": "hxħɦχʁʀ", "r": "rɹɾɻɽɺ", "l": "lɭʎɬʟɮ",
    "f": "fɸ", "v": "vβʋⱱ", "T": "θ", "D": "ð",
}.items():
    for _c in _from:
        _FOLD[_c] = _to
VOWELS = set("aeiouə")


def fold(phones: str) -> str:
    """IPA from the recogniser -> folded alphabet. Length marks, diacritics and spaces are dropped."""
    return "".join(_FOLD.get(c, "") for c in phones)


# How words sound, already folded. A word may have several pronunciations. Words missing here are
# spelled out letter by letter (see _guess), which is good enough for most Portuguese words;
# anything else can be given in config under [listening.sounds].
SOUNDS = {
    "mochi": ["motSi"],
    # a Brazilian "oi" is heard with a rounded start and an open end ("uei", "uai"), and "olá" often
    # without its l: without these, four in ten Portuguese greetings were taken for "hey" or "hi"
    "oi": ["oi", "uei", "uai", "uoi", "oei"], "ola": ["ola", "oa", "ua"],
    "hi": ["hai"], "hey": ["hei"], "hello": ["helo", "həlo"], "alo": ["alo"],
    "e": ["i"], "ai": ["ai"], "bom": ["bo"], "dia": ["dZia"],
    "bye": ["bai"], "goodbye": ["gudbai"], "adeus": ["adeus"], "ate": ["ate"], "logo": ["logu"],
    "tchau": ["tSau", "tSiau", "tSia"],  # "tchau mochi" runs together as "tSianmotSi"
    # "vamos papear" / "let's chat" (the wake phrases of D-48; not in the default config since
    # D-65, kept so they work when configured), as the recogniser wrote 450 spoken clips: "vamos"
    # loses its s ("vamo papear"); the final r of "papear" is rarely
    # there, its e is as often an i, and its second p is now and then a t. The first sound of an
    # utterance is the least reliable one: the v of "vamos" came back as b, d, z, l or not at all,
    # and its a as o, so the cue is also accepted from its vowel on.
    "papear": ["papia", "papea", "papiar", "papie", "patea", "patia"],
    "vamos": ["vamus", "vamos", "vamu", "vomus", "vomos", "vomu", "amus", "omus", "amu", "omu", "bons"],
    "vamo": ["vamu", "vomu", "amu", "omu"],
    "let": ["let", "lit", "lət", "lat"], "chat": ["tSat", "tSet"],
}

_SIMILAR = {  # substitutions that cost less than a full mismatch
    frozenset("ou"): 0.25, frozenset("ei"): 0.25, frozenset("aə"): 0.25, frozenset("eə"): 0.3,
    frozenset("ae"): 0.4, frozenset("SZ"): 0.4, frozenset("td"): 0.4, frozenset("Ss"): 0.5,
    frozenset("tk"): 0.6, frozenset("bp"): 0.4, frozenset("sz"): 0.3, frozenset("gk"): 0.4,
}


@dataclass
class Costs:
    vowel_swap: float = 0.7      # a vowel for an unrelated vowel (closer pairs are in _SIMILAR)
    o_to_schwa: float = 0.6      # "mochi" heard as "muh-chi": kept dear so "how much is it" is not Mochi
    o_to_a: float = 0.5          # "machi"
    m_to_n: float = 0.6          # kept dear so "boa noite" (noitSi) is not Mochi
    drop_vowel: float = 0.5      # expected vowel not heard
    drop_a: float = 0.8          # ...but nobody swallows an "a": "tSi" is not "tchau"
    extra_vowel: float = 0.15    # extra vowel heard (diphthongs: "moatSi", "muotSi", "uoi")
    extra_nasal: float = 0.6     # stray n heard
    drop_t_before_sh: float = 0.15   # "moshi" for "mochi"
    drop_h: float = 0.1
    glued_consonant: float = 0.3     # "bye" is not "hi" with something in front
    gap: float = 0.05            # one stray consonant between the cue and the name (per-phone cost)
    drop_last_vowel: float = 0.25    # utterance-final "motS": Brazilian speakers often swallow the last "i"
    other: float = 1.0


def _guess(word: str) -> str:
    """Letters -> folded phones for a word with no entry in SOUNDS (Portuguese-leaning)."""
    w = word
    for a, b in (("tch", "tS"), ("ch", "S"), ("sh", "S"), ("lh", "li"), ("nh", "ni"), ("qu", "k"), ("ss", "s"),
                 ("rr", "h"), ("ç", "s"), ("c", "k"), ("j", "Z"), ("x", "S"), ("y", "i"), ("w", "u"), ("q", "k")):
        w = w.replace(a, b)
    w = re.sub(r"^r", "h", w)
    return "".join(ch for ch in w if ch in "aeioubdfghklmnprstvzSZ")


def plain(text: str) -> list[str]:
    """Lowercase words without accents or punctuation."""
    text = unicodedata.normalize("NFKD", text.lower())
    return re.findall(r"[a-z]+", "".join(c for c in text if not unicodedata.combining(c)))


@dataclass
class Hit:
    group: str       # "wake" | "goodbye"
    phrase: str      # the configured phrase, e.g. "oi mochi"
    score: float     # 0 = heard exactly, larger = looser match
    heard: str       # the folded phones that matched


class PhraseMatcher:
    def __init__(self, groups: dict[str, list[str]], name: str = "mochi", sounds: dict[str, list[str]] | None = None,
                 name_tolerance: float = 0.45, cue_tolerance: float = 0.3, ignore: list[str] | None = None,
                 careful: tuple[str, ...] = ("goodbye",), costs: Costs | None = None):
        """groups: {"wake": ["oi mochi", "hey mochi"], "goodbye": ["tchau mochi", ...]}. A phrase
        is its anchor (the name when the phrase has it, else its last word) and the cue words before it.

        name_tolerance: how loosely an anchor may be said (edit cost; 0 = exactly as in SOUNDS).
        cue_tolerance: how loosely the word before it may be said (edit cost per phone of that word).
        ignore: words that start with the name's sounds but are not it ("mochila").
        careful: groups never matched generously. A false goodbye would cut a conversation short,
            while a missed one only costs saying it again.
        """
        self.c = costs or Costs()
        self.sounds = {**SOUNDS, **{plain(k)[0]: v for k, v in (sounds or {}).items()}}
        self.name = plain(name)[0]
        self.name_tolerance, self.cue_tolerance = name_tolerance, cue_tolerance
        self.careful = set(careful)
        self.anchors: dict[str, list[str]] = {}  # anchor word -> how it sounds
        self.cues: list[tuple[str, str, str, str]] = []  # (group, phrase, folded cue, anchor)
        for group, phrases in groups.items():
            for phrase in phrases:
                said = plain(phrase)
                anchor = self.name if self.name in said else (said[-1] if said else "")
                words = [w for w in said if w != anchor]
                if not words:
                    continue
                self.anchors.setdefault(anchor, self._prons(anchor))
                for pron in self._phrase_prons(words):
                    self.cues.append((group, " ".join(words + [anchor]), pron, anchor))
        self.name_prons = self.anchors.get(self.name) or self._prons(self.name)
        # what comes right after an anchor's sounds inside each ignored word: "mochila" -> "l"
        self.ignore_next: dict[str, set[str]] = {anchor: set() for anchor in self.anchors}
        for word in ignore or []:
            for pron in self._prons(plain(word)[0]):
                for anchor, apron in ((a, ap) for a, prons in self.anchors.items() for ap in prons):
                    cost, _s, end = min(self._find(apron, pron), default=(9, 0, 0))
                    if cost <= name_tolerance and end < len(pron):
                        self.ignore_next[anchor].add(pron[end])

    def _prons(self, word: str) -> list[str]:
        return self.sounds.get(word) or [_guess(word)]

    def _phrase_prons(self, words: list[str]) -> list[str]:
        out = [""]
        for w in words:
            out = [a + b for a in out for b in self._prons(w)]
        return out

    # --- weighted edit distance -------------------------------------------------------------
    def _sub(self, want: str, got: str) -> float:
        if want == got:
            return 0.0
        pair = frozenset((want, got))
        if pair in _SIMILAR:
            return _SIMILAR[pair]
        if pair == frozenset("mn"):
            return self.c.m_to_n
        if want in VOWELS and got in VOWELS:
            if pair == frozenset("oə") or pair == frozenset("uə"):
                return self.c.o_to_schwa
            if pair == frozenset("oa"):
                return self.c.o_to_a
            return self.c.vowel_swap
        return self.c.other

    def _drop(self, want: str, nxt: str) -> float:
        if want in VOWELS:
            return self.c.drop_a if want == "a" else self.c.drop_vowel
        if want == "t" and nxt == "S":
            return self.c.drop_t_before_sh
        return self.c.drop_h if want == "h" else self.c.other

    def _extra(self, got: str, prev_want: str, next_want: str) -> float:
        """Cost of a heard phone that the phrase does not have, between prev_want and next_want."""
        if got in VOWELS:
            # cheap after a vowel (an off-glide: "moatSi"), beside a like vowel ("muotSi", "uoi") or
            # for a schwa (British "məutSi"); dear elsewhere, so "maiote" is not Mochi
            glide = got == "ə" or prev_want in VOWELS or any(
                w and (w == got or _SIMILAR.get(frozenset((w, got)), 1) <= 0.25) for w in (prev_want, next_want))
            return self.c.extra_vowel if glide else self.c.drop_vowel
        return self.c.extra_nasal if got == "n" else 0.2 if got == "h" else self.c.other

    def _find(self, want: str, heard: str) -> list[tuple[float, int, int]]:
        """Every place `want` occurs in `heard`: (cost, start, end), best alignment per end position."""
        n = len(want)
        # row[j] = (cost, start) of best alignment of want[:j] ending at the current position in heard
        prev = [(0.0, 0)] + [(0.0, 0)] * n
        acc = 0.0
        for j in range(1, n + 1):
            acc += self._drop(want[j - 1], want[j] if j < n else "")
            prev[j] = (acc, 0)
        out = []
        for i in range(1, len(heard) + 1):
            g = heard[i - 1]
            cur = [(0.0, i)] + [(0.0, 0)] * n
            for j in range(1, n + 1):
                w = want[j - 1]
                a = (prev[j - 1][0] + self._sub(w, g), prev[j - 1][1])
                b = (prev[j][0] + self._extra(g, w, want[j] if j < n else ""), prev[j][1])
                c = (cur[j - 1][0] + self._drop(w, want[j] if j < n else ""), cur[j - 1][1])
                cur[j] = min(a, b, c)
            out.append((cur[n][0], cur[n][1], i))
            prev = cur
        return out

    def _cue(self, cue: str, before: str) -> tuple[float, float, int] | None:
        """(cost per phone, cost, phones used) of `cue` against the phones right before the name: it
        must end where the name starts. None when nothing of the cue was heard there."""
        dropped = sum(self._drop(cue[j], cue[j + 1] if j + 1 < len(cue) else "") for j in range(len(cue)))
        gap = 0.0
        if before[-1:] in tuple("nktpdbg"):
            # the closure before "m" is often heard as a stray nasal or stop: "ainmotSi", "oikmotSi"
            before, gap = before[:-1], self.c.gap
        best = min(((c, s) for c, s, e in self._find(cue, before) if e == len(before)), default=None)
        if best is None or best[0] >= dropped:
            return None
        cost, start = best
        # a consonant glued to the front of a vowel-initial cue means another word: "bye" contains
        # "hi", and one lone vowel after a consonant is just a word ending ("comi mochi", "anti-")
        if cue[0] in VOWELS | {"h"} and start > 0 and before[start - 1] not in VOWELS:
            if len(before) - start == 1:
                return None
            cost += self.c.glued_consonant
        elif cue[0] == "h" and 0 < start < len(before) and before[start] != "h" and before[start - 1] in "uo":
            # a rounded vowel in front of a "hey" whose h was not heard is a Brazilian "oi", which
            # arrives as "uei" or "uai": the same sounds, but not the same greeting
            cost += self.c.glued_consonant
        return cost / len(cue) + gap, cost, len(before) - start + (1 if gap else 0)

    # --- public -----------------------------------------------------------------------------
    def match(self, phones: str, final: bool = True, from_start: bool = True) -> Hit | None:
        """phones: what the recogniser heard in one stretch of speech.
        final: the speaker has stopped (otherwise the last phones may still change or grow).
        from_start: the stretch begins where the speaker began (nothing was cut off the front).

        Someone calling Mochi says the phrase on its own or opens a sentence with it, so a phrase
        that ends or begins the stretch is matched generously; one buried mid-sentence must be clean.
        """
        heard = fold(phones)
        best: Hit | None = None
        for anchor, prons in self.anchors.items():
            for pron in prons:
                best = self._match_anchor(anchor, pron, heard, final, from_start, best)
        return best

    def _match_anchor(self, anchor: str, pron: str, heard: str, final: bool, from_start: bool,
                      best: Hit | None) -> Hit | None:
        """The best hit so far, or a better one for this way of saying this anchor."""
        loose = self.name_tolerance + 0.15
        found = self._find(pron, heard)
        if final and pron[-1] in VOWELS:
            found += [(c + self.c.drop_last_vowel, s, e) for c, s, e in self._find(pron[:-1], heard)
                      if e == len(heard)]
        for cost, s, e in found:
            after = len(heard) - e
            # while the speaker is still talking the newest phones are unsettled: wait for three
            # more before deciding, so "a mochi-" can still turn out to be "a mochila"
            if cost > loose or e - s < 3 or (not final and after < 3):
                continue
            if self.ignore_next[anchor] & set(heard[e:e + 2]):
                continue
            is_last = final and after <= 1
            for group, phrase, cue, its_anchor in self.cues:
                if its_anchor != anchor:
                    continue
                got = self._cue(cue, heard[max(0, s - len(cue) - 2):s])
                if got is None:
                    continue
                cc, cue_cost, used = got
                if group in self.careful:  # at most one dropped or swapped vowel in the cue
                    ok = cue_cost <= self.c.drop_vowel and (is_last or cost <= self.name_tolerance)
                elif is_last:
                    ok = cc <= self.cue_tolerance
                elif from_start and s - used <= 1:
                    ok = cc <= self.cue_tolerance and cost <= self.name_tolerance
                else:  # mid-sentence: at most one small slip in the cue
                    ok = cue_cost <= self.cue_tolerance and cost <= self.name_tolerance
                if ok and (best is None or cost + cc < best.score):
                    best = Hit(group, phrase, round(cost + cc, 3), heard[s - used:e])
        return best
