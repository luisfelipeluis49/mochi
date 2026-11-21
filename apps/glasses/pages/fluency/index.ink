<script type="application/json" def>
{
  "navigationBarTitleText": "Mochi AR",
  "description": "Fluency Helper: shows one to three suggested words or phrases, with meanings, when the wearer hesitates.",
  "disableScroll": true
}
</script>

<script setup>
import config from '../../config.js';
import { createConnection, STATUS } from '../../lib/connection.js';
import { createMockSource } from '../../lib/mock-source.js';
import {
  initialState, resetForNewConnection, parseEvent, reduce, expire, dismiss, socketUrl,
} from '../../lib/protocol.js';
import { pickLocale, getStrings } from '../../lib/strings.js';

// One suggestion gets the whole field; two or three share it at one common
// size. The longest phrase decides, so everything stays inside the 480px canvas.
function phraseClass(candidates) {
  const longest = Math.max(...candidates.map((candidate) => candidate.expression.length));
  if (candidates.length === 1) {
    if (longest <= 12) return 'phrase phrase-solo-lg';
    if (longest <= 20) return 'phrase phrase-solo-md';
    return 'phrase phrase-solo-sm';
  }
  return longest <= 18 ? 'phrase phrase-list-lg' : 'phrase phrase-list-sm';
}

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
}

export default {
  data: {
    showHint: false,
    hasContext: false,
    context: '',
    listClass: 'list',
    candidates: [],
    dotClass: 'dot dot-off',
    statusLabel: '',
  },

  onLoad(query) {
    const options = query || {};
    const backendUrl = typeof options.server === 'string' ? options.server : config.backendUrl;
    const userId = text(options.user) || config.userId;
    this._strings = getStrings(pickLocale(navigator.languages));
    this._userId = userId;
    this._detail = '';
    this._state = initialState(userId);
    this._status = STATUS.CONNECTING;
    this._expiryTimer = null;

    let url = '';
    try {
      url = socketUrl(backendUrl, userId);
    } catch (error) {
      // A bare host without a scheme: say so on screen instead of looping.
      console.error('[mochi]', error.message);
      this._badUrl = true;
      this._demo = false;
      this.render();
      return;
    }
    this._demo = url === '';

    const handlers = {
      onMessage: (raw) => this.handleMessage(raw),
      onStatus: (status, detail) => this.handleStatus(status, detail),
    };
    this._source = this._demo
      ? createMockSource(handlers)
      : createConnection({ url, ...handlers });

    console.log(this._demo ? '[mochi] demo mode, no backend set' : `[mochi] connecting as ${userId}`);
    this.render();
  },

  onShow() {
    if (!this._source) return;
    this._state = initialState(this._userId);
    this._source.start();
  },

  onHide() {
    this.stopEverything();
  },

  onUnload() {
    this.stopEverything();
  },

  stopEverything() {
    if (this._source) this._source.stop();
    this.clearExpiryTimer();
  },

  handleStatus(status, detail) {
    this._status = status;
    this._detail = detail || '';
    if (status === STATUS.ONLINE) this._state = resetForNewConnection(this._state);
    this.render();
  },

  handleMessage(raw) {
    const event = parseEvent(raw);
    if (!event) {
      console.warn('[mochi] ignored a message that is not an event');
      return;
    }
    this.apply(reduce(this._state, event, Date.now()));
  },

  // Take a new state: redraw only if it changed, and re-arm the hide timer.
  apply(nextState) {
    if (nextState === this._state) return;
    this._state = nextState;
    this.clearExpiryTimer();
    const hint = nextState.hint;
    if (hint) {
      const wait = Math.max(0, hint.hideAtMs - Date.now());
      this._expiryTimer = setTimeout(() => {
        this._expiryTimer = null;
        this.apply(expire(this._state, Date.now()));
      }, wait);
    }
    this.render();
  },

  clearExpiryTimer() {
    if (this._expiryTimer !== null) {
      clearTimeout(this._expiryTimer);
      this._expiryTimer = null;
    }
  },

  render() {
    const t = this._strings;
    const hint = this._state.hint;

    let label = t.connecting;
    let listening = false;
    if (this._status === STATUS.ONLINE) {
      listening = this._state.capturing;
      label = listening ? t.listening : t.micOff;
    } else if (this._status === STATUS.RECONNECTING) {
      label = t.reconnecting;
    } else if (this._status === STATUS.WAKING_UP) {
      label = t.wakingUp;
    } else if (this._status === STATUS.REJECTED) {
      label = this._detail ? `${t.rejected}: ${this._detail}` : t.rejected;
    }
    if (this._badUrl) label = t.badUrl;
    if (this._demo) label = `${t.demo} - ${label}`;

    const count = hint ? hint.candidates.length : 0;
    const sharedPhraseClass = hint ? phraseClass(hint.candidates) : '';
    const candidates = hint
      ? hint.candidates.map((candidate, index) => ({
        key: `${hint.hintId}-${index}`,
        expression: candidate.expression,
        phraseClass: sharedPhraseClass,
        hasMeaning: candidate.meaning !== '',
        meaning: candidate.meaning,
        meaningClass: count === 1 ? 'meaning meaning-solo' : 'meaning meaning-list',
      }))
      : [];

    this.setData({
      showHint: hint !== null,
      hasContext: hint !== null && hint.context !== '',
      context: hint ? hint.context : '',
      listClass: count === 1 ? 'list list-solo' : 'list list-many',
      candidates,
      dotClass: listening ? 'dot dot-on' : 'dot dot-off',
      statusLabel: label,
    });
  },

  // Enter (temple tap) puts the suggestions away. Back keeps its default.
  onKeyUp(event) {
    if (event.code !== 'Enter' || !this._state.hint) return;
    event.preventDefault();
    this.apply(dismiss(this._state));
  },
};
</script>

<page>
  <view class="stage">
    <view class="hint-area">
      <view class="hint" ink:if="{{showHint}}">
        <text class="context" ink:if="{{hasContext}}">{{context}}</text>
        <view class="{{listClass}}">
          <view class="candidate" ink:for="{{candidates}}" ink:key="key">
            <text class="{{item.phraseClass}}">{{item.expression}}</text>
            <text class="{{item.meaningClass}}" ink:if="{{item.hasMeaning}}">{{item.meaning}}</text>
          </view>
        </view>
      </view>
    </view>

    <view class="status">
      <view class="{{dotClass}}"></view>
      <text class="status-text">{{statusLabel}}</text>
    </view>
  </view>
</page>

<style>
/* Quiet by default: an empty transparent field with one small status line at
   the bottom. Suggestions take the centre and leave again. The suggested
   phrases are the only things at full brightness, so the eye lands on them. */
.stage {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 12px 16px;
}

.hint-area {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.hint {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  animation: mochi-hint-in 200ms ease-out;
}

/* Where the speaker stopped. A reminder, not something to read. */
.context {
  width: 100%;
  text-align: center;
  font-size: 14px;
  line-height: 20px;
  margin-bottom: 16px;
  color: var(--mochi-green-48);
}

.list {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.list-many {
  gap: 14px;
}

.candidate {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.phrase {
  width: 100%;
  text-align: center;
  font-weight: 500;
  color: var(--mochi-green);
}

.phrase-solo-lg {
  font-size: 44px;
  line-height: 52px;
}

.phrase-solo-md {
  font-size: 32px;
  line-height: 40px;
}

.phrase-solo-sm {
  font-size: 24px;
  line-height: 32px;
}

.phrase-list-lg {
  font-size: 26px;
  line-height: 32px;
}

.phrase-list-sm {
  font-size: 20px;
  line-height: 26px;
}

.meaning {
  width: 100%;
  text-align: center;
  color: var(--mochi-green-72);
}

.meaning-solo {
  font-size: 18px;
  line-height: 26px;
  margin-top: 10px;
}

.meaning-list {
  font-size: 14px;
  line-height: 20px;
}

/* Status: a label plus a dot shape (solid = Mochi is listening, hollow = it
   is not), so the state never depends on brightness alone. */
.status {
  height: 16px;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 3px;
  box-sizing: border-box;
}

.dot-on {
  background-color: var(--mochi-green-72);
}

.dot-off {
  border: 1px solid var(--mochi-green-48);
}

.status-text {
  font-size: 12px;
  line-height: 16px;
  color: var(--mochi-green-48);
}

@keyframes mochi-hint-in {
  0% { opacity: 0; }
  100% { opacity: 1; }
}
</style>
