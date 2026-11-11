# Bluetooth Keep Awake

An NVDA add-on that keeps Bluetooth speakers and headphones awake by
continuously playing a near-silent sound, so they do not disconnect or fall
asleep during quiet moments.

## Commands

- NVDA+Shift+B: toggle keep-awake on or off.
- NVDA+Shift+Alt+B: change the sound: quiet low tone (30 hertz), quiet high
  tone (19 kilohertz) or true silence.
- NVDA+Control+Shift+B: change the tone volume.

## Notes

- The tones are meant to be inaudible. The low tone is below most small
  speakers' range; the high tone is above most adults' hearing.
- True digital silence does not keep every device awake. If your speaker
  still sleeps in true silence mode, use one of the tones.
- The sound plays through the same audio device NVDA uses.
- Requires NVDA 2023.2 or later (tested on 2026.1).

## License

GNU General Public License v2 or later. See LICENSE.
