#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Random BYTES → {BPSK, GMSK, GFSK} (baseband) → QtGUI Freq/Time (3 traces)
#
# Radioconda / Windows (GNU Radio 3.10/3.11):
#   conda install -c conda-forge gnuradio pyqt
#
import os
from gnuradio import gr, blocks, qtgui, digital
from gnuradio.filter import rational_resampler_ccc

# ---- Window enum (cross-version) ----
try:
    from gnuradio.fft import window
    WINTYPE = window.WIN_HAMMING
except Exception:
    try:
        from gnuradio.filter import firdes
        WINTYPE = firdes.WIN_HAMMING
    except Exception:
        WINTYPE = 6  # last-resort enum

# ---- Qt / SIP ----
from PyQt5 import Qt
try:
    import sip
except Exception:
    from PyQt5 import sip  # rare fallback

def wrap_qt_widget(obj):
    """Works for GR 3.8–3.11 (qwidget vs pyqwidget)."""
    try:
        w = obj.qwidget()
    except AttributeError:
        w = obj.pyqwidget()
    return sip.wrapinstance(w, Qt.QWidget)

class top_block(gr.top_block, Qt.QWidget):
    def __init__(self):
        gr.top_block.__init__(self, "Random {BPSK, GMSK, GFSK} → Qt Sinks (SIM)")
        Qt.QWidget.__init__(self)
        self.setWindowTitle("BPSK vs GMSK vs GFSK — Frequency / Time (sim)")

        # ---- Parameters ----
        self.samp_rate = 200_000   # samples/s (GUI & throttles)
        self.bit_rate  = 10_000    # bits/s
        self.sps = int(self.samp_rate // self.bit_rate)  # samples-per-symbol (≈20)
        if self.sps < 2:
            raise RuntimeError(
                f"samp_rate={self.samp_rate} must be ≥ 2× bit_rate={self.bit_rate} (got sps={self.sps})"
            )

        # G(M)FSK shaping
        self.gmsk_bt = 0.30
        self.gfsk_bt = 0.50      # set to 0.30 if you want the same BT as GMSK
        self.gfsk_sensitivity = 1.0  # works fine for comparison; adjust if desired

        # ---- Layout ----
        layout = Qt.QVBoxLayout(self)

        # Shared Frequency sink (3 inputs)
        self.freq = qtgui.freq_sink_c(
            1024, WINTYPE, 0.0, self.samp_rate,
            "Spectrum (baseband, 0 Hz center)", 3
        )
        self.freq.set_update_time(0.10)
        self.freq.enable_autoscale(True)
        self.freq.set_line_label(0, "BPSK")
        self.freq.set_line_label(1, "GMSK (BT=%.2f)" % self.gmsk_bt)
        self.freq.set_line_label(2, "GFSK (BT=%.2f)" % self.gfsk_bt)
        layout.addWidget(wrap_qt_widget(self.freq))

        # Shared Time sink (3 inputs)
        self.time = qtgui.time_sink_c(
            1024, self.samp_rate, "Time Domain (baseband)", 3
        )
        self.time.set_update_time(0.10)
        self.time.set_line_label(0, "BPSK")
        self.time.set_line_label(1, "GMSK")
        self.time.set_line_label(2, "GFSK")
        layout.addWidget(wrap_qt_widget(self.time))

        # ---- Random byte source (repeatable) ----
        rand_bytes = list(os.urandom(20_000))
        self.src = blocks.vector_source_b(rand_bytes, True)  # repeat=True

        # Bytes → bits
        self.unpack = blocks.unpack_k_bits_bb(8)

        # ---------- BPSK branch ----------
        bpsk_map = [-1.0+0.0j, 1.0+0.0j]
        self.bpsk_sym = digital.chunks_to_symbols_bc(bpsk_map)  # bits→complex
        self.bpsk_gain = blocks.multiply_const_cc(1.0)
        self.bpsk_up = rational_resampler_ccc(
            interpolation=self.sps, decimation=1, taps=[], fractional_bw=0.0
        )
        self.bpsk_throttle = blocks.throttle(gr.sizeof_gr_complex, self.samp_rate, True)

        # ---------- GMSK branch ----------
        # digital.gmsk_mod(samples_per_symbol, bt, verbose=False, log=False)
        self.gmsk = digital.gmsk_mod(self.sps, self.gmsk_bt, False, False)
        self.gmsk_throttle = blocks.throttle(gr.sizeof_gr_complex, self.samp_rate, True)

        # ---------- GFSK branch ----------
        # Prefer digital.gfsk_mod; fallback to gmsk_mod if not present.
        try:
            # digital.gfsk_mod(samples_per_symbol, sensitivity, bt, verbose=False, log=False)
            self.gfsk = digital.gfsk_mod(self.sps, self.gfsk_sensitivity, self.gfsk_bt, False, False)
        except AttributeError:
            # approximate with GMSK mod (note: not identical to GFSK)
            self.gfsk = digital.gmsk_mod(self.sps, self.gfsk_bt, False, False)
        self.gfsk_throttle = blocks.throttle(gr.sizeof_gr_complex, self.samp_rate, True)

        # ---- Connections ----
        # Fan-out bits to all three modulators
        self.connect(self.src, self.unpack)

        # BPSK chain
        self.connect(self.unpack, self.bpsk_sym)
        self.connect(self.bpsk_sym, self.bpsk_gain)
        self.connect(self.bpsk_gain, self.bpsk_up)
        self.connect(self.bpsk_up, self.bpsk_throttle)

        # GMSK chain (expects 0/1 bytes)
        self.connect(self.unpack, self.gmsk)
        self.connect(self.gmsk, self.gmsk_throttle)

        # GFSK chain (expects 0/1 bytes)
        self.connect(self.unpack, self.gfsk)
        self.connect(self.gfsk, self.gfsk_throttle)

        # To shared sinks (map inputs 0,1,2)
        self.connect(self.bpsk_throttle, (self.freq, 0))
        self.connect(self.gmsk_throttle, (self.freq, 1))
        self.connect(self.gfsk_throttle, (self.freq, 2))

        self.connect(self.bpsk_throttle, (self.time, 0))
        self.connect(self.gmsk_throttle, (self.time, 1))
        self.connect(self.gfsk_throttle, (self.time, 2))

def main():
    qapp = Qt.QApplication([])
    tb = top_block()
    tb.start()
    tb.show()
    qapp.exec_()
    tb.stop()
    tb.wait()

if __name__ == "__main__":
    main()
