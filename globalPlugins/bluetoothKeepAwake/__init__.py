# Bluetooth Keep Awake
# An NVDA add-on that keeps Bluetooth speakers and headphones awake by
# continuously playing a near-silent sound.
#
# Copyright (C) 2026 arvin
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import math
import struct

import wx

import addonHandler
import config
import globalPluginHandler
import nvwave
import scriptHandler
import ui
from logHandler import log

addonHandler.initTranslation()

SAMPLE_RATE = 22050
CHUNK_SECONDS = 0.5
FEED_INTERVAL_MS = 300

# Sound modes: (spoken name, frequency in Hz or None for true digital silence).
# True digital silence does not keep every device awake; the tones are the
# reliable option. The low tone is below most small speakers' range, the high
# tone is above most adults' hearing.
MODES = [
	("quiet low tone, 30 hertz", 30),
	("quiet high tone, 19 kilohertz", 19000),
	("true silence", None),
]

# Amplitude levels as a fraction of full scale. 1% is usually inaudible on
# laptop and headphone speakers at normal volume, but raise it if a device
# still sleeps.
LEVELS = [0.005, 0.01, 0.02, 0.05]


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = "Bluetooth Keep Awake"

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		self._player = None
		self._enabled = False
		self._modeIndex = 0
		self._levelIndex = 1  # 1%
		self._chunk = None
		self._failed = False
		self._generation = 0

	def terminate(self):
		self._stopFeeding()
		super(GlobalPlugin, self).terminate()

	def _buildChunk(self):
		"""Precompute one chunk of PCM data for the current mode and level."""
		freq = MODES[self._modeIndex][1]
		if freq is None:
			self._chunk = b"\x00" * int(SAMPLE_RATE * CHUNK_SECONDS) * 2
			return
		amp = LEVELS[self._levelIndex]
		# Use a whole number of periods when the period is an integer number
		# of samples, so looped chunks do not click.
		period = SAMPLE_RATE / freq
		target = SAMPLE_RATE * CHUNK_SECONDS
		if abs(period - round(period)) < 1e-9:
			period = int(round(period))
			n = max(period, int(round(target / period)) * period)
		else:
			n = int(target)
		buf = bytearray()
		for i in range(n):
			v = int(32767 * amp * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
			buf += struct.pack("<h", v)
		self._chunk = bytes(buf)

	def _startFeeding(self):
		if self._player is not None:
			return True
		# config.conf["audio"]["outputDevice"] is the output device setting,
		# verified in NVDA 2026.1 source (configSpec [audio] section). The old
		# [speech] outputDevice key no longer exists and raises KeyError.
		deviceName = config.conf["audio"]["outputDevice"]
		try:
			self._player = self._createPlayer(deviceName)
		except Exception as firstError:
			# The configured device may be gone (Bluetooth off); retry once on
			# the system default device before giving up.
			log.warning(
				"Bluetooth Keep Awake: opening device %r failed (%s), retrying default device",
				deviceName, firstError, exc_info=True,
			)
			try:
				self._player = self._createPlayer("")
			except Exception as secondError:
				log.warning("Bluetooth Keep Awake: default device also failed", exc_info=True)
				self._player = None
				# Translators: error detail with the audio device name and the system error.
				self._lastError = _("device {device}: {error}").format(
					device=deviceName or _("default"), error=secondError,
				)
				return False
		self._buildChunk()
		generation = self._generation
		wx.CallLater(FEED_INTERVAL_MS, self._pump, generation)
		return True

	def _createPlayer(self, deviceName):
		return nvwave.WavePlayer(
			channels=1,
			samplesPerSec=SAMPLE_RATE,
			bitsPerSample=16,
			outputDevice=deviceName,
			wantDucking=False,
			purpose=nvwave.AudioPurpose.SOUNDS,
		)

	def _stopFeeding(self):
		self._enabled = False
		self._generation += 1  # invalidate any pending pump timer
		if self._player is not None:
			try:
				self._player.close()
			except Exception:
				log.debugWarning("Bluetooth Keep Awake: error closing player", exc_info=True)
			self._player = None

	def _pump(self, generation):
		if generation != self._generation:
			return
		if not self._enabled or self._player is None:
			return
		try:
			self._player.feed(self._chunk)
		except Exception:
			log.debugWarning("Bluetooth Keep Awake: error feeding audio", exc_info=True)
			if not self._failed:
				self._failed = True
				# Translators: announced when the audio device fails while active.
				ui.message(_("Bluetooth keep awake: audio device error"))
			self._stopFeeding()
			return
		wx.CallLater(FEED_INTERVAL_MS, self._pump, generation)

	@scriptHandler.script(
		# Translators: input help message for the keep-awake toggle command.
		description=_("Toggles continuous near-silent audio that keeps Bluetooth speakers and headphones awake"),
		gestures=["kb:NVDA+windows+b"],
	)
	def script_toggleKeepAwake(self, gesture):
		if self._enabled:
			self._stopFeeding()
			# Translators: announced when keep-awake audio stops.
			ui.message(_("Bluetooth keep awake off"))
			return
		self._failed = False
		if self._startFeeding():
			self._enabled = True
			# Translators: announced when keep-awake audio starts. {mode} is the sound mode.
			ui.message(_("Bluetooth keep awake on, {mode}").format(mode=MODES[self._modeIndex][0]))
		else:
			# Translators: announced when the audio device could not be opened. {error} is the actual error detail.
			ui.message(_("Bluetooth keep awake: could not open the audio device, {error}").format(
				error=getattr(self, "_lastError", _("unknown error")),
			))

	@scriptHandler.script(
		# Translators: input help message for the sound mode command.
		description=_("Cycles the keep-awake sound between a quiet low tone, a quiet high tone and true silence"),
		gestures=["kb:NVDA+shift+alt+b"],
	)
	def script_cycleMode(self, gesture):
		self._modeIndex = (self._modeIndex + 1) % len(MODES)
		if self._enabled:
			self._buildChunk()
		# Translators: announced when the keep-awake sound mode changes. {mode} is the sound mode.
		ui.message(_("Bluetooth keep awake mode: {mode}").format(mode=MODES[self._modeIndex][0]))

	@scriptHandler.script(
		# Translators: input help message for the volume level command.
		description=_("Cycles the keep-awake tone volume"),
		gestures=["kb:NVDA+control+shift+b"],
	)
	def script_cycleLevel(self, gesture):
		self._levelIndex = (self._levelIndex + 1) % len(LEVELS)
		if self._enabled and MODES[self._modeIndex][1] is not None:
			self._buildChunk()
		percent = LEVELS[self._levelIndex] * 100
		# Translators: announced when the keep-awake tone volume changes. {percent} is the level in percent.
		ui.message(_("Bluetooth keep awake volume: {percent} percent").format(percent=percent))
