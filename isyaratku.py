"""
IsyaratKu - Prototipe Deteksi Gestur Real-time
===============================================

Program ini membaca gerakan satu tangan dari webcam, mengenali beberapa
gestur sederhana menggunakan aturan heuristik, lalu menerjemahkannya menjadi
teks dan suara.

Catatan penting:
    Program ini adalah prototipe edukasi untuk tugas HCI. Aturan yang dipakai
    belum dimaksudkan sebagai penerjemah Bahasa Isyarat Indonesia (BISINDO)
    atau SIBI yang lengkap dan resmi.
"""

# Queue dipakai sebagai jalur komunikasi yang aman antara thread utama video
# dan thread khusus Text-to-Speech. Dengan begitu, proses suara tidak menahan
# proses pembacaan frame webcam.
from queue import Empty, Queue

# Thread digunakan secara eksplisit agar pyttsx3 berjalan di latar belakang.
from threading import Event, Thread

# Time digunakan untuk menerapkan cooldown suara dan menghitung FPS.
from time import perf_counter

import cv2
import mediapipe as mp
import pyttsx3


# ---------------------------------------------------------------------------
# KONFIGURASI APLIKASI
# ---------------------------------------------------------------------------

# Nomor kamera default. Jika komputer memiliki lebih dari satu kamera, angka
# ini dapat diubah menjadi 1, 2, dan seterusnya.
CAMERA_INDEX = 0

# Resolusi yang cukup ringan untuk laptop, tetapi tetap nyaman untuk deteksi.
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

# Jeda minimal antarsuara. Nilai ini mencegah suara yang sama diputar terus
# menerus ketika tangan masih berada pada pose yang sama.
SPEECH_COOLDOWN_SECONDS = 3.0

# Jumlah frame berturut-turut yang harus memiliki hasil sama sebelum sebuah
# gestur dianggap stabil. Ini membantu mengurangi kedipan label karena noise.
STABLE_FRAMES_REQUIRED = 5

# Warna antarmuka OpenCV menggunakan format BGR, bukan RGB.
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_CYAN = (255, 220, 0)
COLOR_GREEN = (70, 220, 90)
COLOR_YELLOW = (0, 220, 255)
COLOR_RED = (60, 70, 235)
COLOR_PANEL = (28, 35, 48)


# ---------------------------------------------------------------------------
# WORKER TEXT-TO-SPEECH
# ---------------------------------------------------------------------------

class SpeechWorker:
    """Menjalankan pyttsx3 dalam thread terpisah dari loop webcam."""

    def __init__(self):
        # Queue menyimpan kalimat yang perlu diucapkan secara berurutan.
        self._speech_queue = Queue()

        # Event ini menjadi sinyal agar thread dapat berhenti dengan rapi.
        self._stop_event = Event()

        # Thread dibuat daemon supaya proses tidak menggantung ketika program
        # utama berhenti secara tidak sengaja.
        self._thread = Thread(target=self._run, name="IsyaratKu-TTS", daemon=True)

        # Status ini membantu program tetap berjalan walaupun driver suara
        # gagal diinisialisasi pada komputer tertentu.
        self.available = True

    def start(self):
        """Memulai thread suara."""
        self._thread.start()

    def speak(self, text):
        """Mengantrekan teks baru untuk diucapkan."""
        if self.available and text:
            self._speech_queue.put(text)

    def stop(self):
        """Meminta thread suara berhenti dan menunggu sebentar."""
        self._stop_event.set()
        self._speech_queue.put(None)

        # Join memberi kesempatan pada pyttsx3 menyelesaikan proses penutupan.
        # Timeout mencegah aplikasi macet jika driver audio bermasalah.
        self._thread.join(timeout=2.0)

    def _run(self):
        """Fungsi yang dieksekusi di thread khusus Text-to-Speech."""
        pythoncom = None

        # Pada Windows, pyttsx3 biasanya menggunakan SAPI5 yang berbasis COM.
        # Inisialisasi COM di thread ini membantu menghindari error COM ketika
        # engine dibuat bukan dari thread utama.
        try:
            import pythoncom  # Disediakan oleh paket pywin32 jika tersedia.

            pythoncom.CoInitialize()
        except ImportError:
            # pywin32 bersifat opsional. pyttsx3 tetap dicoba pada platform
            # atau konfigurasi yang tidak menyediakan modul pythoncom.
            pythoncom = None
        except Exception as error:
            print(f"[PERINGATAN] COM tidak dapat diinisialisasi: {error}")
            pythoncom = None

        engine = None

        try:
            # Engine sengaja dibuat di dalam thread, bukan di __init__.
            # Pola ini lebih aman untuk driver SAPI5 pada Windows.
            engine = pyttsx3.init()
            engine.setProperty("rate", 165)
            engine.setProperty("volume", 1.0)
        except Exception as error:
            # Kegagalan audio tidak boleh menghentikan tampilan webcam.
            self.available = False
            print(f"[PERINGATAN] Text-to-Speech tidak tersedia: {error}")

        try:
            # Thread terus menunggu kalimat baru selama aplikasi masih hidup.
            while not self._stop_event.is_set():
                try:
                    # Timeout membuat thread dapat memeriksa stop_event secara
                    # berkala walaupun tidak ada kalimat di dalam queue.
                    text = self._speech_queue.get(timeout=0.1)
                except Empty:
                    continue

                # None adalah penanda khusus untuk menutup worker.
                if text is None:
                    break

                # Jika engine gagal dibuat, teks cukup diabaikan dan video
                # tetap berjalan normal.
                if engine is None:
                    continue

                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception as error:
                    print(f"[PERINGATAN] Gagal mengucapkan '{text}': {error}")
        finally:
            # Meminta engine berhenti agar resource audio dilepas.
            if engine is not None:
                try:
                    engine.stop()
                except Exception:
                    pass

            # COM harus dilepas oleh thread yang sebelumnya melakukan
            # CoInitialize. Pengecekan dilakukan agar aman di platform lain.
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# LOGIKA DETEKSI JARI DAN GESTUR
# ---------------------------------------------------------------------------

def is_thumb_open(hand_landmarks, handedness_label):
    """Menentukan apakah ibu jari terbuka berdasarkan arah koordinat X."""
    # Landmark ibu jari yang digunakan:
    # 4 = ujung jari dan 3 = sendi terakhir sebelum ujung jari.
    thumb_tip = hand_landmarks.landmark[4]
    thumb_ip = hand_landmarks.landmark[3]

    # Arah horizontal ibu jari bergantung pada tangan kiri atau kanan.
    # Toleransi kecil mengurangi perubahan status akibat getaran tangan.
    horizontal_margin = 0.02

    if handedness_label == "Right":
        return thumb_tip.x < thumb_ip.x - horizontal_margin

    return thumb_tip.x > thumb_ip.x + horizontal_margin


def get_finger_states(hand_landmarks, handedness_label):
    """
    Mengembalikan status [ibu jari, telunjuk, jari tengah, manis, kelingking].

    Untuk empat jari selain ibu jari, jari dianggap terbuka jika koordinat Y
    ujung jari lebih kecil daripada koordinat Y sendi PIP. Pada gambar OpenCV,
    nilai Y yang lebih kecil berarti posisi yang lebih tinggi di layar.
    """
    landmarks = hand_landmarks.landmark

    # Ibu jari bergerak terutama ke arah samping, sehingga dibandingkan pada
    # sumbu X melalui fungsi khusus di atas.
    thumb_open = is_thumb_open(hand_landmarks, handedness_label)

    # Pasangan (ujung jari, sendi PIP) untuk telunjuk sampai kelingking.
    finger_pairs = ((8, 6), (12, 10), (16, 14), (20, 18))
    finger_states = [thumb_open]

    # Selisih 0.02 adalah margin sederhana untuk menghindari jari yang hampir
    # lurus dianggap berubah-ubah hanya karena noise landmark.
    vertical_margin = 0.02
    for tip_index, pip_index in finger_pairs:
        tip_y = landmarks[tip_index].y
        pip_y = landmarks[pip_index].y
        finger_states.append(tip_y < pip_y - vertical_margin)

    return finger_states


def classify_gesture(finger_states):
    """Menerjemahkan kombinasi status jari menjadi nama gestur."""
    thumb, index, middle, ring, pinky = finger_states

    # Semua jari terbuka: gestur sapaan yang mudah dikenali.
    if all(finger_states):
        return "Halo"

    # Tidak ada jari terbuka: tangan mengepal.
    if not any(finger_states):
        return "Tunggu"

    # Hanya ibu jari terbuka.
    if thumb and not index and not middle and not ring and not pinky:
        return "Oke"

    # Telunjuk dan jari tengah terbuka: simbol damai.
    if index and middle and not thumb and not ring and not pinky:
        return "Damai"

    # Hanya telunjuk terbuka: gestur menunjuk.
    if index and not thumb and not middle and not ring and not pinky:
        return "Tunjuk"

    # Kombinasi lain belum didaftarkan sebagai gestur pada prototipe ini.
    return "Tidak dikenali"


# ---------------------------------------------------------------------------
# UTILITAS TAMPILAN DAN STABILISASI
# ---------------------------------------------------------------------------

def draw_text_box(frame, text, origin, font_scale=0.7, color=COLOR_WHITE,
                  background=COLOR_PANEL, thickness=2):
    """Menggambar teks dengan panel latar agar tetap terbaca di atas video."""
    x, y = origin
    font = cv2.FONT_HERSHEY_SIMPLEX
    (text_width, text_height), baseline = cv2.getTextSize(
        text, font, font_scale, thickness
    )

    # Padding membuat teks tidak menempel langsung ke tepi panel.
    padding_x = 12
    padding_y = 9
    top_left = (x - padding_x, y - text_height - padding_y)
    bottom_right = (
        x + text_width + padding_x,
        y + baseline + padding_y,
    )

    # Rectangle solid meningkatkan kontras teks terhadap latar webcam.
    cv2.rectangle(frame, top_left, bottom_right, background, -1)
    cv2.putText(frame, text, (x, y), font, font_scale, color, thickness,
                cv2.LINE_AA)


def draw_interface(frame, gesture, fps, cooldown_remaining, speech_status):
    """Menggambar feedback visual dan instruksi penggunaan di layar."""
    height, width = frame.shape[:2]

    # Panel transparan sederhana di bagian atas memberi hierarki visual yang
    # jelas tanpa menutupi seluruh area video.
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (width, 126), COLOR_PANEL, -1)
    cv2.addWeighted(overlay, 0.88, frame, 0.12, 0, frame)

    # Nama aplikasi menjadi identitas utama prototipe.
    cv2.putText(frame, "ISYARATKU", (24, 38), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, COLOR_CYAN, 2, cv2.LINE_AA)
    cv2.putText(frame, "Real-time Hand Gesture Translator", (24, 68),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_WHITE, 1, cv2.LINE_AA)

    # Hasil terjemahan dibuat paling besar agar menjadi feedback utama bagi
    # pengguna, sesuai prinsip visibility of system status dalam HCI.
    result_color = COLOR_GREEN if gesture != "Tidak dikenali" else COLOR_YELLOW
    draw_text_box(frame, f"GESTUR: {gesture}", (24, 112), 0.78,
                  result_color, (35, 45, 60), 2)

    # Informasi teknis ditempatkan di kanan atas agar tidak mengganggu hasil.
    cv2.putText(frame, f"FPS: {fps:05.1f}", (width - 170, 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_WHITE, 1, cv2.LINE_AA)
    cv2.putText(frame, f"TTS: {speech_status}", (width - 170, 62),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_GREEN if speech_status == "AKTIF" else COLOR_RED,
                1, cv2.LINE_AA)

    if cooldown_remaining > 0:
        cooldown_text = f"Suara siap dalam {cooldown_remaining:.1f}s"
        cv2.putText(frame, cooldown_text, (width - 270, 96),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, COLOR_YELLOW, 1, cv2.LINE_AA)

    # Footer berisi instruksi operasional yang selalu terlihat.
    footer_y = height - 22
    cv2.putText(frame, "Tunjukkan satu tangan  |  Q: keluar  |  R: reset gestur",
                (24, footer_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                COLOR_WHITE, 1, cv2.LINE_AA)


def open_camera():
    """Membuka webcam dengan backend yang sesuai dengan sistem operasi."""
    # CAP_DSHOW sering membantu Windows membuka webcam lebih cepat dan
    # mengurangi konflik backend pada beberapa driver kamera.
    if hasattr(cv2, "CAP_DSHOW"):
        camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        if camera.isOpened():
            return camera

        # Fallback ke backend default jika DirectShow tidak tersedia.
        camera.release()

    return cv2.VideoCapture(CAMERA_INDEX)


# ---------------------------------------------------------------------------
# PROGRAM UTAMA
# ---------------------------------------------------------------------------

def main():
    """Menjalankan seluruh alur input, proses, feedback, dan output."""
    camera = open_camera()

    # Validasi awal memberi pesan yang lebih jelas daripada error OpenCV yang
    # muncul jauh setelah program berjalan.
    if not camera.isOpened():
        raise RuntimeError(
            "Webcam tidak dapat dibuka. Periksa izin kamera atau ubah CAMERA_INDEX."
        )

    # Mengatur ukuran frame sebelum loop dimulai agar performa lebih konsisten.
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    # Alias pendek agar kode deteksi lebih mudah dibaca.
    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles

    # Worker suara dimulai satu kali dan dipakai sepanjang aplikasi berjalan.
    speech_worker = SpeechWorker()
    speech_worker.start()

    # Variabel untuk stabilisasi gestur dan cooldown suara.
    candidate_gesture = "Tidak dikenali"
    candidate_count = 0
    stable_gesture = "Menunggu tangan..."
    last_spoken_gesture = None
    last_spoken_at = -float("inf")
    last_frame_at = perf_counter()
    fps = 0.0

    try:
        # MediaPipe Hands mendeteksi maksimal satu tangan agar fokus prototipe
        # tetap sederhana dan hasil gesture tidak ambigu.
        with mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.65,
            min_tracking_confidence=0.65,
        ) as hands:
            while True:
                # Membaca satu frame dari webcam.
                success, frame = camera.read()
                if not success:
                    print("[PERINGATAN] Frame webcam tidak berhasil dibaca.")
                    break

                # Tampilan selfie lebih natural untuk pengguna karena gerakan
                # tangan terasa seperti melihat cermin.
                frame = cv2.flip(frame, 1)

                # FPS dihitung dengan exponential smoothing agar angka di UI
                # tidak bergetar terlalu tajam setiap frame.
                now = perf_counter()
                frame_delta = max(now - last_frame_at, 1e-6)
                current_fps = 1.0 / frame_delta
                fps = (0.9 * fps) + (0.1 * current_fps) if fps else current_fps
                last_frame_at = now

                # MediaPipe memerlukan citra RGB, sedangkan OpenCV membaca BGR.
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb_frame.flags.writeable = False
                results = hands.process(rgb_frame)
                rgb_frame.flags.writeable = True

                detected_gesture = "Tidak dikenali"

                if results.multi_hand_landmarks:
                    hand_landmarks = results.multi_hand_landmarks[0]

                    # Menggambar skeleton tangan sebagai feedback visual.
                    mp_drawing.draw_landmarks(
                        frame,
                        hand_landmarks,
                        mp_hands.HAND_CONNECTIONS,
                        mp_drawing_styles.get_default_hand_landmarks_style(),
                        mp_drawing_styles.get_default_hand_connections_style(),
                    )

                    # Label handedness membantu logika ibu jari mengetahui arah
                    # horizontal yang benar untuk tangan kiri atau kanan.
                    handedness_label = "Right"
                    if results.multi_handedness:
                        handedness_label = results.multi_handedness[0].classification[0].label

                    finger_states = get_finger_states(hand_landmarks, handedness_label)
                    detected_gesture = classify_gesture(finger_states)

                    # Stabilizer hanya menerima gestur yang sama selama beberapa
                    # frame agar label dan suara tidak sensitif terhadap noise.
                    if detected_gesture == candidate_gesture:
                        candidate_count += 1
                    else:
                        candidate_gesture = detected_gesture
                        candidate_count = 1

                    if candidate_count >= STABLE_FRAMES_REQUIRED:
                        stable_gesture = detected_gesture
                else:
                    # Ketika tangan hilang, status dibuat informatif tanpa
                    # langsung memicu suara baru.
                    candidate_gesture = "Tidak dikenali"
                    candidate_count = 0
                    stable_gesture = "Menunggu tangan..."

                # Suara hanya dipicu untuk gestur yang terdaftar dan sudah
                # melewati cooldown dari suara sebelumnya.
                current_time = perf_counter()
                cooldown_remaining = max(
                    0.0,
                    SPEECH_COOLDOWN_SECONDS - (current_time - last_spoken_at),
                )
                can_speak = cooldown_remaining <= 0
                is_valid_gesture = stable_gesture in {
                    "Halo", "Tunggu", "Oke", "Damai", "Tunjuk"
                }

                # Hanya ucapkan ketika gestur stabil berubah. Ini mencegah
                # pengulangan suara walaupun cooldown sudah selesai.
                if is_valid_gesture and stable_gesture != last_spoken_gesture and can_speak:
                    speech_worker.speak(stable_gesture)
                    last_spoken_gesture = stable_gesture
                    last_spoken_at = current_time
                    cooldown_remaining = SPEECH_COOLDOWN_SECONDS

                # Status audio di UI menunjukkan apakah engine berhasil dibuat.
                speech_status = "AKTIF" if speech_worker.available else "NONAKTIF"
                draw_interface(
                    frame,
                    stable_gesture,
                    fps,
                    cooldown_remaining,
                    speech_status,
                )

                # Menampilkan frame hasil deteksi.
                cv2.imshow("IsyaratKu - Deteksi Gestur Real-time", frame)

                # waitKey wajib dipanggil agar window OpenCV tetap responsif.
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("r"):
                    # Reset manual memungkinkan pengguna mengulangi gestur yang
                    # sama tanpa menunggu perubahan pose yang lain.
                    last_spoken_gesture = None
                    last_spoken_at = -float("inf")
                    stable_gesture = "Menunggu tangan..."
                    candidate_gesture = "Tidak dikenali"
                    candidate_count = 0

    finally:
        # Semua resource ditutup walaupun terjadi error atau pengguna menutup
        # aplikasi melalui tombol close pada window.
        camera.release()
        speech_worker.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nIsyaratKu dihentikan oleh pengguna.")
    except Exception as error:
        print(f"[ERROR] {error}")
