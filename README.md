# ISYARATKU

## Prototipe HCI — Deteksi Gestur Real-time untuk Aksesibilitas

**IsyaratKu** adalah prototipe Human-Computer Interaction (HCI) yang
menggunakan webcam untuk mengenali gestur tangan sederhana, menerjemahkannya
menjadi teks, lalu membacakannya melalui suara secara real-time.

Proyek ini dirancang sebagai demonstrasi teknologi yang lebih inklusif bagi
penyandang disabilitas tuli atau bisu. Sistem dibuat ringan dengan pendekatan
heuristik sehingga dapat dijalankan tanpa melatih model machine learning
eksternal.

> **Status proyek:** Prototipe akademik untuk tugas HCI — bukan penerjemah
> Bahasa Isyarat Indonesia (BISINDO/SIBI) resmi.

## Fitur Utama

- Deteksi tangan real-time menggunakan webcam.
- Pelacakan 21 landmark tangan dengan MediaPipe Hands.
- Klasifikasi gestur berbasis perbandingan koordinat ujung jari dan sendi.
- Terjemahan visual langsung pada jendela video.
- Text-to-Speech offline menggunakan `pyttsx3`.
- Thread khusus suara agar tampilan video tidak freeze atau lagging.
- Cooldown suara untuk mencegah output berulang terlalu cepat.
- Stabilizer frame untuk mengurangi kedipan hasil deteksi.
- Antarmuka visual dengan feedback, status TTS, FPS, dan instruksi keyboard.

## Gestur yang Didukung

| Gestur tangan | Hasil teks dan suara |
|---|---|
| Lima jari terbuka | Halo |
| Tangan mengepal | Tunggu |
| Hanya ibu jari terbuka | Oke |
| Telunjuk dan jari tengah terbuka | Damai |
| Hanya telunjuk terbuka | Tunjuk |

## Konsep Berpikir HCI

```text
INPUT
  Webcam menangkap gerakan tangan pengguna
       ↓
PROSES
  OpenCV membaca frame
  MediaPipe menemukan 21 landmark tangan
  Heuristik memeriksa posisi ujung jari dan sendi
  Stabilizer memastikan gestur cukup konsisten
       ↓
OUTPUT
  Gestur tampil sebagai teks di layar
  Gestur dibacakan melalui Text-to-Speech offline
```

Sistem memberikan feedback visual yang terus terlihat sehingga pengguna dapat
mengetahui apakah tangan terdeteksi, gestur apa yang terbaca, berapa FPS yang
berjalan, dan apakah Text-to-Speech sedang aktif. Hal ini menerapkan prinsip
HCI berupa *visibility of system status*.

## Manfaat untuk Masyarakat

Komunikasi sehari-hari tidak selalu mudah bagi penyandang disabilitas tuli atau
bisu, terutama ketika berinteraksi dengan orang yang belum memahami bahasa
isyarat. IsyaratKu mencoba menjadi jembatan komunikasi sederhana: pengguna
menunjukkan gestur, kemudian komputer memberikan teks dan suara yang dapat
dipahami oleh orang di sekitarnya.

Prototipe ini juga dapat menjadi media belajar bagi mahasiswa untuk memahami
hubungan antara kamera, computer vision, desain feedback, aksesibilitas, dan
interaksi manusia-komputer.

## Teknologi yang Digunakan

- Python 3.9 atau lebih baru
- OpenCV (`opencv-python`)
- MediaPipe (`mediapipe`)
- pyttsx3 (`pyttsx3`)
- Threading dan Queue dari standard library Python

## Instalasi

Pastikan Python dan webcam sudah tersedia, kemudian jalankan perintah berikut
di terminal pada folder proyek:

```bash
python -m pip install --upgrade pip
python -m pip install opencv-python mediapipe pyttsx3
```

### Windows — rekomendasi tambahan

Driver suara Windows menggunakan SAPI5. Jika muncul error COM atau suara tidak
keluar, pasang dukungan `pywin32`:

```bash
python -m pip install pywin32
```

## Cara Menjalankan

```bash
python isyaratku.py
```

Setelah jendela kamera terbuka:

- Tunjukkan satu tangan ke arah webcam.
- Pastikan tangan berada di area yang cukup terang.
- Tunggu sampai gestur stabil beberapa frame.
- Tekan `Q` untuk keluar.
- Tekan `R` untuk mereset gestur dan mengulangi suara.

Jika webcam tidak terbuka, ubah nilai berikut pada bagian konfigurasi
`isyaratku.py`:

```python
CAMERA_INDEX = 0
```

Contohnya, gunakan `1` jika webcam yang diinginkan terdaftar sebagai kamera
kedua.

## Struktur Proyek

```text
.
├── isyaratku.py
└── README.md
```

## Catatan Teknis

Program menggunakan aturan heuristik, bukan model machine learning yang
dilatih khusus. Artinya, hasil dapat dipengaruhi oleh pencahayaan, sudut
tangan, jarak dari kamera, resolusi webcam, dan variasi bentuk tangan.

Thread Text-to-Speech diinisialisasi secara terpisah dari thread video. Pada
Windows, program juga mencoba menginisialisasi COM di thread suara untuk
mengurangi kemungkinan error pada driver SAPI5.

## Disclaimer Akademik

IsyaratKu dibuat untuk demonstrasi dan evaluasi konsep HCI. Sistem ini belum
divalidasi sebagai alat bantu komunikasi medis, sosial, atau penerjemah bahasa
isyarat resmi. Untuk penggunaan nyata, diperlukan dataset yang representatif,
validasi bersama pengguna disabilitas, pengujian aksesibilitas, serta kolaborasi
dengan ahli bahasa isyarat dan praktisi terkait.

## Lisensi

Proyek ini dapat dikembangkan lebih lanjut untuk kebutuhan pembelajaran dan
demonstrasi akademik.
