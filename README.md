# Favera Model 1 AI Service V0.2

Implementasi modular untuk:

- Global Ranker V4 sebagai **extreme-risk ranking signal**
- Personal Anomaly V0
- Rule Engine V0
- Provisional Fusion V0
- Model 1 Orchestrator
- FastAPI untuk integrasi Express.js

Tidak ada komponen yang menyatakan transaksi sebagai perjudian. Output aplikasi adalah
`attention_score`, `attention_level`, `requires_confirmation`, dan reason codes.

## Struktur folder

```text
favera-ai/
├── app/
│   ├── __init__.py
│   ├── global_ranker.py
│   ├── personal_anomaly.py
│   ├── rule_engine.py
│   ├── reason_codes.py
│   ├── fusion.py
│   ├── orchestrator.py
│   ├── factory.py
│   ├── schemas.py
│   └── main.py
├── artifacts/
│   └── global_ranker_v4_momtsim_v1/
├── config/
│   ├── global_ranker_v4.json
│   ├── personal_anomaly_v0.json
│   ├── rule_engine_v0.json
│   └── fusion_v0.json
├── examples/
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

## Peran Global Ranker V4

Global V4 tidak dipakai sebagai classifier mandiri karena threshold eksperimen
menghasilkan alert rate terlalu tinggi. Adapter hanya mengeluarkan sinyal kuat saat:

```text
global_percentile >= 0.99
```

Di bawah percentile tersebut, outputnya `NO_STRONG_GLOBAL_SIGNAL`.

## Artefak V4

Letakkan file hasil export notebook di:

```text
artifacts/global_ranker_v4_momtsim_v1/
```

Nama default:

```text
global_ranker_v4.joblib
feature_contract_v4.json
calibration_score_reference_v4.npy
model_metadata_v4.json
```

Sebelum feature builder produksi tersedia, request dapat mengirim `global_features`
yang sudah sesuai dengan `feature_contract_v4.json`. Bila global features atau artefak
belum tersedia, orchestrator tetap berjalan memakai personal anomaly dan rule engine.

## Menjalankan lokal

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install dan test:

```bash
pip install -r requirements.txt
pytest -q
```

Demo tanpa artefak:

```bash
python -m examples.run_orchestrator
```

FastAPI:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Dokumentasi endpoint:

```text
http://127.0.0.1:8000/docs
```

Endpoint:

```text
GET  /health
GET  /version
POST /v1/model1/evaluate
POST /v1/model1/evaluate-batch
```

## Fusion V0

Fusion masih provisional dan belum dikalibrasi end-to-end. Keputusan konfirmasi
menggunakan gate yang transparan:

- critical rule,
- strong global dengan dukungan personal,
- strong global dengan dukungan rule,
- personal sangat tinggi dengan dukungan rule,
- atau minimal dua sinyal independen pada weighted confirmation score.

Strong global sendirian tidak memaksa konfirmasi.

## Langkah berikutnya

1. Verifikasi artefak V4 lokal.
2. Jalankan API end-to-end dengan Express.js.
3. Audit dan bangun notebook global score MoMTSim V2.
4. Tambahkan `feature_builder.py` setelah feature contract global V2 final.
5. Kalibrasi fusion pada data end-to-end, bukan dengan tebakan bobot permanen.

