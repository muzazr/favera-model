# HANDOFF CONTEXT — FAVERA TRANSACTION ANOMALY (MODEL 1)

## 0. Tujuan handoff

Lanjutkan pekerjaan **langsung pada folder lokal yang sudah ada**.

Jangan membuat project baru.
Jangan membuat ZIP baru.
Jangan mengganti struktur folder tanpa alasan teknis.
Jangan mengasumsikan isi file. Baca file lokal terlebih dahulu.

Source of truth lokal saat ini:

```text
favera-ai-model/
```

---

## 1. Peran dan batas tanggung jawab

Pemilik project saat ini bekerja sebagai **FE + AI Engineer**, tetapi fokus pekerjaan sekarang adalah **AI Engineer**.

Fokus AI:

- training dan evaluasi global model;
- personal anomaly;
- rule engine;
- score fusion;
- reason codes;
- feature engineering;
- model artifacts;
- batch inference;
- response AI yang sesuai kontrak tim.

Backend menangani:

- Express.js public API;
- autentikasi;
- database;
- persistence;
- queue/job;
- retry/idempotency;
- pemanggilan AI service;
- endpoint publik untuk Flutter.

AI tetap perlu menyediakan fungsi inference yang stabil dan menghasilkan response sesuai kontrak internal.

---

## 2. Arsitektur Model 1 yang disepakati

```text
Canonical transactions
        ↓
Feature engineering
        ↓
Global transaction risk ranker
        ↓
Personal anomaly model
        ↓
Rule engine
        ↓
Score fusion
        ↓
Reason codes
        ↓
Anomaly assessment per transaction
        ↓
User confirmation
```

Model tidak boleh:

- menyatakan transaksi sebagai transaksi judi;
- menyamakan fraud sintetis dengan gambling;
- menuduh pengguna;
- membuat keputusan keluarga otomatis.

Terminologi produk aman:

- transaksi tidak biasa;
- memerlukan perhatian;
- memerlukan konfirmasi;
- berbeda dari pola sebelumnya.

---

## 3. Folder lokal saat ini

Struktur yang terlihat dan harus dianggap sebagai source of truth:

```text
favera-ai-model/
├── app/
│   ├── __init__.py
│   ├── factory.py
│   ├── fusion.py
│   ├── global_ranker.py
│   ├── main.py
│   ├── orchestrator.py
│   ├── personal_anomaly.py
│   ├── reason_codes.py
│   ├── rule_engine.py
│   └── schemas.py
│
├── artifacts/
│   └── global_ranker_v4_momtsim_v1/
│       ├── benchmark_results_v4.csv
│       ├── calibration_score_reference_v4.npy
│       ├── calibration_threshold_v4.json
│       ├── evaluation_metrics_v4.json
│       ├── feature_contract_v4.json
│       ├── feature_diagnostic_v4.csv
│       ├── feature_importance_v4.csv
│       ├── global_ranker_v4.joblib
│       ├── model_metadata_v4.json
│       ├── top_fraction_thresholds_v4.json
│       └── top_k_metrics_v4.csv
│
├── config/
│   ├── fusion_v0.json
│   ├── global_ranker_v4.json
│   ├── personal_anomaly_v0.json
│   └── rule_engine_v0.json
│
├── examples/
│   ├── __init__.py
│   ├── run_components.py
│   └── run_orchestrator.py
│
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_fusion.py
│   ├── test_global_ranker.py
│   ├── test_orchestrator.py
│   ├── test_personal_anomaly.py
│   └── test_rule_engine.py
│
├── .env.example
├── README.md
└── requirements.txt
```

Catatan penting:

- Folder ini **belum boleh diasumsikan** sudah sepenuhnya contract-aligned.
- Jangan memakai folder atau ZIP lain sebagai source of truth.
- Baca isi file lokal yang ada sebelum patch.

---

## 4. Status Global Ranker V4

Dataset:

```text
MoMTSim V1
```

Model:

```text
LightGBM
```

Role yang disepakati:

```text
global extreme-risk ranker
```

Bukan classifier final aplikasi.

Temuan penting:

- ranker cukup berguna pada transaksi paling ekstrem;
- threshold classifier menghasilkan alert rate terlalu tinggi;
- threshold hasil calibration tetap artefak eksperimen;
- jangan menjadikannya keputusan produk otomatis.

Hasil clean consistency run terakhir:

```text
test_summary_v4 alert_rate                  = 0.732887
test_predictions_v4.mean                    = 0.732887
weighted_test_temporal_diagnostic alert_rate = 0.732887
```

Ketiganya konsisten.

Temuan top-fraction:

```text
calibration percentile >= 0.99
→ STRONG_GLOBAL_SIGNAL
```

Top 1% relatif stabil dan precision tinggi.

Area 95–99% tidak cukup kuat untuk disebut supporting signal.

Rekomendasi global signal:

```text
percentile >= 0.99
→ STRONG_GLOBAL_SIGNAL

percentile < 0.99
→ NO_STRONG_GLOBAL_SIGNAL
```

Jangan memakai:

```text
95–99% → SUPPORTING_SIGNAL
```

kecuali nanti ada validasi baru.

Output global yang ideal secara internal:

```json
{
  "global_probability": 0.0,
  "global_percentile": 0.0,
  "global_signal_level": "STRONG_GLOBAL_SIGNAL | NO_STRONG_GLOBAL_SIGNAL",
  "model_version": "..."
}
```

Untuk API contract final, map ke:

```text
global_model_score
```

dan simpan percentile/signal sebagai diagnostic internal bila tidak ada field kontraknya.

---

## 5. Personal Anomaly V0

File:

```text
app/personal_anomaly.py
config/personal_anomaly_v0.json
```

Desain V0 deterministic, bukan trained model.

Komponen yang direncanakan:

- amount deviation berbasis median/MAD;
- recipient novelty;
- velocity anomaly;
- unusual time;
- repeated amount;
- balance impact;
- cold-start / history confidence.

Saat histori belum cukup:

```text
personal_baseline_status = insufficient_history
personal_model_score = null
```

Personal score tidak seharusnya ikut fusion sebagai score yang dianggap valid ketika cold-start.

Tetapi reason code berikut boleh tetap keluar:

```text
LIMITED_USER_HISTORY
```

---

## 6. Rule Engine V0

File:

```text
app/rule_engine.py
config/rule_engine_v0.json
```

Rule yang direncanakan:

- NEW_RECIPIENT_HIGH_AMOUNT
- AMOUNT_ABOVE_PERSONAL_BASELINE
- HIGH_TRANSACTION_VELOCITY
- BALANCE_NEARLY_DEPLETED
- LARGE_BALANCE_IMPACT
- REPEATED_SAME_AMOUNT
- UNUSUAL_TRANSACTION_TIME
- LIMITED_USER_HISTORY

Rule engine harus:

- deterministic;
- explainable;
- versioned;
- tidak menyatakan fraud atau gambling.

Household context pada API contract:

- essential_budget_remaining
- unconfirmed_transaction_count
- large_transaction_threshold
- active_goal_progress

Jangan menambahkan formula baru sembarangan.
Kalau context belum dipakai, dokumentasikan sebagai belum dipakai.
Kalau dipakai, gunakan rule sederhana, configurable, dan explainable.

---

## 7. Fusion V0

File:

```text
app/fusion.py
config/fusion_v0.json
```

Fusion saat ini masih provisional.

Prinsip:

- bobot tidak boleh diklaim final;
- global, personal, dan rule score harus tersedia per komponen;
- missing component harus menyebabkan weight redistribution yang eksplisit;
- cold-start personal harus dianggap unavailable;
- global unavailable harus fail-open, bukan mematikan semua inference.

Global strong signal sendirian sebaiknya tidak otomatis menjadi needs_confirmation tanpa dukungan lain, kecuali rule kritis.

Risk band API contract:

```text
normal
unusual
needs_confirmation
```

---

## 8. API contract final tim

Kontrak final internal:

```text
favera-ai-service-v0.1.openapi.json
```

Flutter tidak berbicara langsung ke AI service.

Alur:

```text
Flutter
→ Express.js
→ AI service / AI inference
```

Untuk sisi AI, fokus utama adalah fungsi batch inference yang mengikuti kontrak.

Input:

```json
{
  "request_id": "string",
  "user_id": "uuid",
  "family_id": "uuid",
  "current_transactions": [],
  "historical_transactions": [],
  "household_context": {
    "essential_budget_remaining": 0,
    "unconfirmed_transaction_count": 0,
    "large_transaction_threshold": 0,
    "active_goal_progress": 0.0
  }
}
```

Canonical transaction:

```json
{
  "transaction_id": "uuid",
  "transaction_at": "ISO-8601 datetime",
  "direction": "income | expense | transfer",
  "amount": 0,
  "currency": "IDR",
  "description": "...",
  "counterparty_name": null,
  "counterparty_id": null,
  "category": "...",
  "payment_channel": null,
  "balance_before": null,
  "balance_after": null,
  "external_transaction_id": null,
  "source_provider": "mandiri | bri | gopay | other"
}
```

Response per transaction:

```json
{
  "transaction_id": "uuid",
  "anomaly_score": 0.0,
  "risk_band": "normal | unusual | needs_confirmation",
  "reason_codes": [],
  "reason_details": [
    {
      "code": "...",
      "feature": "...",
      "observed_value": null,
      "baseline_value": null,
      "explanation": "..."
    }
  ],
  "recommended_action": "...",
  "personal_baseline_status": "available | insufficient_history | not_applicable",
  "global_model_score": null,
  "personal_model_score": null,
  "rule_score": null,
  "model_version": "...",
  "preprocessing_version": "..."
}
```

Batch response:

```json
{
  "request_id": "...",
  "assessments": [],
  "processing_ms": 0
}
```

Kontrak menggunakan:

```text
additionalProperties: false
```

Jadi output final tidak boleh menambah field seenaknya.

Backend mengurus endpoint dan auth.
AI cukup menyediakan pure function stabil, misalnya:

```python
assess_batch(payload) -> AnomalyBatchResponse
```

FastAPI wrapper boleh ada, tetapi bukan fokus utama saat ini.

---

## 9. Mapping canonical transaction ke modul internal

Modul lama mungkin memakai:

```text
timestamp
recipient_id
transaction_type
```

Kontrak memakai:

```text
transaction_at
counterparty_id
category / direction
```

Jangan mengganti seluruh personal/rule implementation hanya untuk rename field.

Gunakan adapter:

```text
transaction_at  → timestamp
counterparty_id → recipient_id
category        → transaction_type internal bila perlu
```

Backend tidak boleh mengirim `global_features`.

Global feature engineering harus tetap dilakukan di sisi AI.

---

## 10. Batasan deployability

Data e-statement realistis menyediakan:

- transaction_at;
- description;
- amount;
- direction;
- user balance;
- category/merchant hasil ekstraksi;
- payment channel jika tersedia;
- counterparty bila berhasil diekstraksi.

Tidak tersedia secara umum:

- old_bal_recipient;
- new_bal_recipient;
- recipient_balance_change;
- recipient_balance_error;
- amount_to_recipient_balance_ratio;
- recipient_old_balance_zero.

Jangan memasukkan fitur recipient balance ke production feature contract.

---

## 11. Tugas pertama Antigravity di lokal

Lakukan langkah berikut secara berurutan.

### A. Inspect, jangan langsung rewrite

Baca seluruh isi:

```text
app/factory.py
app/global_ranker.py
app/orchestrator.py
app/fusion.py
app/schemas.py
app/reason_codes.py
app/main.py
app/personal_anomaly.py
app/rule_engine.py
```

Baca juga:

```text
config/*.json
tests/*.py
README.md
```

### B. Jalankan baseline lokal

```bash
cd favera-ai-model
python -m venv .venv
```

Aktifkan environment, lalu:

```bash
pip install -r requirements.txt
pytest -q
python -m examples.run_orchestrator
```

Catat:

- test yang gagal;
- artifact yang gagal dimuat;
- schema mismatch;
- runtime error;
- actual output JSON.

### C. Verifikasi artifact loading

Pastikan `factory.py` dan `global_ranker.py` membaca file yang benar:

```text
artifacts/global_ranker_v4_momtsim_v1/global_ranker_v4.joblib
artifacts/global_ranker_v4_momtsim_v1/feature_contract_v4.json
artifacts/global_ranker_v4_momtsim_v1/calibration_score_reference_v4.npy
artifacts/global_ranker_v4_momtsim_v1/model_metadata_v4.json
artifacts/global_ranker_v4_momtsim_v1/top_fraction_thresholds_v4.json
```

Jangan mengandalkan file name yang tidak ada.

### D. Bandingkan actual inference dengan API contract

Fokus pada:

- input batch;
- canonical transaction fields;
- output `AnomalyAssessment`;
- nullable component scores;
- risk band enum;
- reason details;
- no extra fields.

### E. Patch minimal

Jangan membuat folder baru.
Jangan membuat ZIP baru.
Patch langsung folder lokal.

Prioritas patch:

1. pure `assess_batch(payload)` function;
2. canonical schema;
3. contract adapter;
4. batch temporal processing;
5. response mapper;
6. feature builder interface;
7. tests.

### F. Temporal safety

`historical_transactions` hanya berisi transaksi sebelum current transaction.

Untuk batch current:

- process secara chronological;
- current transaction yang lebih awal boleh menjadi histori transaksi berikutnya;
- transaksi dengan timestamp sama tidak menjadi histori satu sama lain;
- response order tetap mengikuti request order.

### G. Global builder

Karena backend tidak mengirim `global_features`, buat interface:

```python
build_global_features(
    transaction,
    history,
    household_context
)
```

Tetapi jangan mengarang implementasi production bila pipeline notebook belum diekstrak dengan benar.

Fallback aman:

```text
global_model_score = null
```

sambil personal + rules tetap berjalan.

---

## 12. Eksperimen MoMTSim V2

Belum mulai sebelum inference baseline lokal diverifikasi.

Setelah local inference dan contract response stabil:

- duplicate notebook V4 menjadi notebook V2 challenger;
- audit schema V2;
- rebuild features dari raw V2;
- temporal split baru;
- calibration baru;
- compare dengan V1;
- export artifacts baru;
- jangan overwrite V1 artifacts.

Nama yang disarankan:

```text
global_ranker_v5_momtsim_v2/
```

Jangan memakai hasil Antigravity lama yang menampilkan PR-AUC hampir 1.0 tanpa audit leakage.

Audit wajib:

- schema;
- row count;
- label distribution;
- fraud per transaction type;
- user/entity leakage;
- temporal split;
- duplicate rows;
- future information;
- deployable features;
- top-k stability;
- calibration;
- false alert rate.

---

## 13. Larangan penting

Jangan:

- membuat project baru;
- mengirim ZIP baru;
- mengganti seluruh arsitektur;
- mengubah personal/rule logic tanpa audit;
- menganggap artifact tersedia hanya karena folder ada;
- memakai test set untuk threshold;
- memakai V1 threshold langsung pada V2;
- memakai recipient balance production;
- menyebut score sebagai probabilitas judi;
- mengklaim production-ready dari data sintetis.

---

## 14. Definition of done untuk fase lokal berikutnya

Fase dianggap selesai bila:

1. `pytest -q` lulus;
2. `python -m examples.run_orchestrator` jalan;
3. artifact V4 berhasil dimuat atau fallback-nya eksplisit;
4. ada pure `assess_batch(payload)`;
5. input dan output sesuai API contract;
6. tidak ada `global_features` dari backend;
7. cold-start menghasilkan:
   - `personal_baseline_status = insufficient_history`
   - `personal_model_score = null`
8. output memakai:
   - `normal`
   - `unusual`
   - `needs_confirmation`
9. response tidak memiliki field di luar contract;
10. semua perubahan dilakukan langsung pada `favera-ai-model/`.

---

## 15. Dokumen rujukan

Gunakan sebagai source of truth:

```text
README-contract-decisions.md
favera-ai-service-v0.1.openapi.json
master-context.txt
running_notebook_favera_v3.pdf
GEMASTIK_Technical_Brief_AI_Datasets.pdf
```

Ketika isi lokal bertentangan dengan asumsi, percayai:

1. file lokal aktual;
2. API contract final;
3. master context;
4. baru kemudian handoff ini.
