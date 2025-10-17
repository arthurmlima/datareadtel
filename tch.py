#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Random BYTES → {BPSK, GMSK, GFSK} (baseband) + AWGN → QtGUI (Freq/Time)
# Live "indexes": Bitrate, per-branch Signal Power (dB), SNR (dB)
#
# Radioconda / Windows (GNU Radio 3.10/3.11):
#   conda install -c conda-forge gnuradio pyqt
#
import os, math
from gnuradio import gr, blocks, qtgui, digital, analog
from gnuradio.filter import rational_resampler_ccc
from PyQt5 import Qt
try:
    import sip
except Exception:
    from PyQt5 import sip  # rare fallback

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

def wrap_qt_widget(obj):
    """Works for GR 3.8–3.11 (qwidget vs pyqwidget)."""
    try:
        w = obj.qwidget()
    except AttributeError:
        w = obj.pyqwidget()
    return sip.wrapinstance(w, Qt.QWidget)

def db10(x, eps=1e-12):
    x = max(x, eps)
    return 10.0 * math.log10(x)

class top_block(gr.top_block, Qt.QWidget):
    def __init__(self):
        gr.top_block.__init__(self, "Random {BPSK, GMSK, GFSK} → Qt Sinks (SIM)")
        Qt.QWidget.__init__(self)
        self.setWindowTitle("BPSK vs GMSK vs GFSK — Spectrum / Time + Indexes")

        # ===== Parameters =====
        self.samp_rate = 200_000     # samples/s (GUI & throttles)
        self.bit_rate  = 10_000      # bits/s
        self.sps = int(self.samp_rate // self.bit_rate)   # samples-per-symbol (≈20)
        if self.sps < 2:
            raise RuntimeError(
                f"samp_rate={self.samp_rate} must be ≥ 2× bit_rate={self.bit_rate} (got sps={self.sps})"
            )

        # Noise / SNR control
        self.target_snr_db = 20.0    # desired SNR (approx). Change here.
        # For unit-power signals, complex AWGN sigma ~~ 10^(-SNR/20)/sqrt(2)
        self.noise_sigma = (10.0 ** (-self.target_snr_db / 20.0)) / math.sqrt(2.0)

        # G(M)FSK shaping
        self.gmsk_bt = 0.30
        self.gfsk_bt = 0.50
        self.gfsk_sensitivity = 1.0

        # ===== Layout =====
        layout = Qt.QVBoxLayout(self)

        # Header / index label (updated by a timer)
        self.header = Qt.QLabel("", self)
        self.header.setStyleSheet("font-weight:600;")
        layout.addWidget(self.header)

        # Frequency sink (3 inputs)
        self.freq = qtgui.freq_sink_c(
            1024, WINTYPE, 0.0, self.samp_rate,
            "Spectrum (baseband, 0 Hz center)", 3
        )
        self.freq.set_update_time(0.10)
        self.freq.enable_autoscale(True)
        self.freq.set_line_label(0, "BPSK")
        self.freq.set_line_label(1, f"GMSK (BT={self.gmsk_bt:.2f})")
        self.freq.set_line_label(2, f"GFSK (BT={self.gfsk_bt:.2f})")
        layout.addWidget(wrap_qt_widget(self.freq))

        # Time sink (3 inputs)
        self.time = qtgui.time_sink_c(1024, self.samp_rate, "Time Domain (baseband)", 3)
        self.time.set_update_time(0.10)
        self.time.set_line_label(0, "BPSK")
        self.time.set_line_label(1, "GMSK")
        self.time.set_line_label(2, "GFSK")
        layout.addWidget(wrap_qt_widget(self.time))

        # ===== Source: random bytes (repeat) =====
        rand_bytes = list(os.urandom(20_000))
        self.src = blocks.vector_source_b(rand_bytes, True)
        self.unpack = blocks.unpack_k_bits_bb(8)  # bytes → bits

        # ======== BPSK branch ========
        bpsk_map = [-1.0+0.0j, 1.0+0.0j]
        self.bpsk_sym  = digital.chunks_to_symbols_bc(bpsk_map)
        self.bpsk_gain = blocks.multiply_const_cc(1.0)
        self.bpsk_up   = rational_resampler_ccc(interpolation=self.sps, decimation=1, taps=[], fractional_bw=0.0)

        # Add noise and throttle (noisy signal goes to sinks)
        self.bpsk_noise = analog.noise_source_c(analog.GR_GAUSSIAN, self.noise_sigma, 0)
        self.bpsk_add   = blocks.add_cc()
        self.bpsk_throt = blocks.throttle(gr.sizeof_gr_complex, self.samp_rate, True)

        # Measurements (signal & noise powers → probes)
        self.bpsk_mag2_sig   = blocks.complex_to_mag_squared(1)
        self.bpsk_avg_sig    = blocks.moving_average_ff(1024, 1.0/1024.0, 4000)
        self.bpsk_probe_sig  = blocks.probe_signal_f()

        self.bpsk_sub_noise  = blocks.sub_cc()  # noisy - clean
        self.bpsk_mag2_noise = blocks.complex_to_mag_squared(1)
        self.bpsk_avg_noise  = blocks.moving_average_ff(1024, 1.0/1024.0, 4000)
        self.bpsk_probe_noise= blocks.probe_signal_f()

        # ======== GMSK branch ========
        self.gmsk_mod  = digital.gmsk_mod(self.sps, self.gmsk_bt, False, False)
        self.gmsk_noise= analog.noise_source_c(analog.GR_GAUSSIAN, self.noise_sigma, 1)
        self.gmsk_add  = blocks.add_cc()
        self.gmsk_throt= blocks.throttle(gr.sizeof_gr_complex, self.samp_rate, True)

        self.gmsk_mag2_sig   = blocks.complex_to_mag_squared(1)
        self.gmsk_avg_sig    = blocks.moving_average_ff(1024, 1.0/1024.0, 4000)
        self.gmsk_probe_sig  = blocks.probe_signal_f()

        self.gmsk_sub_noise  = blocks.sub_cc()
        self.gmsk_mag2_noise = blocks.complex_to_mag_squared(1)
        self.gmsk_avg_noise  = blocks.moving_average_ff(1024, 1.0/1024.0, 4000)
        self.gmsk_probe_noise= blocks.probe_signal_f()

        # ======== GFSK branch ========
        try:
            self.gfsk_mod = digital.gfsk_mod(self.sps, self.gfsk_sensitivity, self.gfsk_bt, False, False)
        except AttributeError:
            # Fallback: approximate with GMSK if GFSK mod block is unavailable
            self.gfsk_mod = digital.gmsk_mod(self.sps, self.gfsk_bt, False, False)

        self.gfsk_noise= analog.noise_source_c(analog.GR_GAUSSIAN, self.noise_sigma, 2)
        self.gfsk_add  = blocks.add_cc()
        self.gfsk_throt= blocks.throttle(gr.sizeof_gr_complex, self.samp_rate, True)

        self.gfsk_mag2_sig   = blocks.complex_to_mag_squared(1)
        self.gfsk_avg_sig    = blocks.moving_average_ff(1024, 1.0/1024.0, 4000)
        self.gfsk_probe_sig  = blocks.probe_signal_f()

        self.gfsk_sub_noise  = blocks.sub_cc()
        self.gfsk_mag2_noise = blocks.complex_to_mag_squared(1)
        self.gfsk_avg_noise  = blocks.moving_average_ff(1024, 1.0/1024.0, 4000)
        self.gfsk_probe_noise= blocks.probe_signal_f()

        # ===== Connections =====
        # Fan-out bits
        self.connect(self.src, self.unpack)

        # --- BPSK chain ---
        self.connect(self.unpack, self.bpsk_sym)
        self.connect(self.bpsk_sym, self.bpsk_gain, self.bpsk_up)
        # measure signal power (clean)
        self.connect(self.bpsk_up, self.bpsk_mag2_sig, self.bpsk_avg_sig, self.bpsk_probe_sig)
        # add noise → noisy
        self.connect(self.bpsk_up, (self.bpsk_add, 0))
        self.connect(self.bpsk_noise, (self.bpsk_add, 1))
        # measure noise power as (noisy - clean)
        self.connect(self.bpsk_add, (self.bpsk_sub_noise, 0))
        self.connect(self.bpsk_up,  (self.bpsk_sub_noise, 1))
        self.connect(self.bpsk_sub_noise, self.bpsk_mag2_noise, self.bpsk_avg_noise, self.bpsk_probe_noise)
        # throttle & to sinks
        self.connect(self.bpsk_add, self.bpsk_throt)
        self.connect(self.bpsk_throt, (self.freq, 0))
        self.connect(self.bpsk_throt, (self.time, 0))

        # --- GMSK chain ---
        self.connect(self.unpack, self.gmsk_mod)
        # measure signal power (clean)
        self.connect(self.gmsk_mod, self.gmsk_mag2_sig, self.gmsk_avg_sig, self.gmsk_probe_sig)
        # add noise → noisy
        self.connect(self.gmsk_mod, (self.gmsk_add, 0))
        self.connect(self.gmsk_noise, (self.gmsk_add, 1))
        # measure noise power
        self.connect(self.gmsk_add, (self.gmsk_sub_noise, 0))
        self.connect(self.gmsk_mod, (self.gmsk_sub_noise, 1))
        self.connect(self.gmsk_sub_noise, self.gmsk_mag2_noise, self.gmsk_avg_noise, self.gmsk_probe_noise)
        # throttle & to sinks
        self.connect(self.gmsk_add, self.gmsk_throt)
        self.connect(self.gmsk_throt, (self.freq, 1))
        self.connect(self.gmsk_throt, (self.time, 1))

        # --- GFSK chain ---
        self.connect(self.unpack, self.gfsk_mod)
        # measure signal power (clean)
        self.connect(self.gfsk_mod, self.gfsk_mag2_sig, self.gfsk_avg_sig, self.gfsk_probe_sig)
        # add noise → noisy
        self.connect(self.gfsk_mod, (self.gfsk_add, 0))
        self.connect(self.gfsk_noise, (self.gfsk_add, 1))
        # measure noise power
        self.connect(self.gfsk_add, (self.gfsk_sub_noise, 0))
        self.connect(self.gfsk_mod, (self.gfsk_sub_noise, 1))
        self.connect(self.gfsk_sub_noise, self.gfsk_mag2_noise, self.gfsk_avg_noise, self.gfsk_probe_noise)
        # throttle & to sinks
        self.connect(self.gfsk_add, self.gfsk_throt)
        self.connect(self.gfsk_throt, (self.freq, 2))
        self.connect(self.gfsk_throt, (self.time, 2))

        # ===== Live index updater =====
        self._timer = Qt.QTimer(self)
        self._timer.timeout.connect(self._update_indexes)
        self._timer.start(500)  # ms
        self._update_indexes()  # prime

    def _update_indexes(self):
        # Read moving-avg powers from probes
        b_sig = self.bpsk_probe_sig.level()
        b_noi = self.bpsk_probe_noise.level()
        g_sig = self.gmsk_probe_sig.level()
        g_noi = self.gmsk_probe_noise.level()
        f_sig = self.gfsk_probe_sig.level()
        f_noi = self.gfsk_probe_noise.level()

        # Convert to dB and SNR dB
        b_p_db = db10(b_sig)
        g_p_db = db10(g_sig)
        f_p_db = db10(f_sig)

        b_snr_db = db10(b_sig / max(b_noi, 1e-12))
        g_snr_db = db10(g_sig / max(g_noi, 1e-12))
        f_snr_db = db10(f_sig / max(f_noi, 1e-12))

        text = (
            f"Bitrate: {self.bit_rate} bps | SPS: {self.sps} | Target SNR: {self.target_snr_db:.1f} dB\n"
            f"BPSK  → P={b_p_db:6.2f} dB, SNR={b_snr_db:6.2f} dB    "
            f"GMSK  → P={g_p_db:6.2f} dB, SNR={g_snr_db:6.2f} dB    "
            f"GFSK  → P={f_p_db:6.2f} dB, SNR={f_snr_db:6.2f} dB"
        )
        self.header.setText(text)

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
