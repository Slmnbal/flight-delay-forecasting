# Modelleme: plan adı → kod adı eşlemesi

- **Tarih:** 2026-11-19 · **Kapsam:** M3 modelleme, adım 1 (bölmeler, özellikler, hedefler, baseline'lar, metrikler)
- **Dayanak:** `experiments/modelleme-plani.md`; veri katmanı adları için `deliverables/data/LAYER_SCHEMA.md` (oradaki eşleme geçerli, burada tekrarlanmadı).
- Kod paketi: `deliverables/src/flight_delay/modeling/`. Kod İngilizce, plan Türkçe; aşağıdaki tablo tek eşleme kaynağıdır.
- Bu belgede performans sayısı yoktur. Kod henüz çalıştırılmadı.

## Modüller ve dosyalar

| Plan adı | Kod adı | Not |
|---|---|---|
| `bolme.py` (§1.5) | `flight_delay/modeling/splits.py` | Bölme tarihlerinin tek kaynağı |
| `ozellik_sozlesmesi.py` | `flight_delay/data/feature_contract.py` | Var olan modül; değiştirilmedi |
| özellik üretimi (§2.3) | `flight_delay/modeling/features.py` | |
| geçmiş istatistikler / hedef kodlama (§2.4) | `flight_delay/modeling/history.py` | |
| hedefler (§3) | `flight_delay/modeling/targets.py` | |
| baseline'lar (§4.1) | `flight_delay/modeling/baselines.py` | |
| metrikler (§5.1) | `flight_delay/modeling/metrics.py` | yalnızca numpy |
| ay ay okuma | `flight_delay/modeling/loading.py` | son test bölümlerini açmaz |
| baseline çalıştırıcı | `flight_delay/modeling/run_baselines.py` | çıktı: `experiments/baselines/run-<zaman>/` |
| `son_test.py` (§1.5) | `flight_delay/modeling/run_final_test.py` (`--final` / `--rehearsal`) | 2026-11-21; değerlendirme çekirdeği `final_eval.py`, gün blok bootstrap + Holm `bootstrap.py`; kurallar `experiments/son-test-on-kayit.md` |
| kilit girdisi (dondurulanlar) | `flight_delay/modeling/final_lock.py` (`draft_manifest`, `load_manifest`) | örn. `experiments/son-test-dondurma.json` |
| takvim özelliği kuralı (D adımı) | `flight_delay/modeling/calendar_rule.py` | yalnızca Val-A |
| `arayuz_ciktisi.py` | — | sonraki çalıştırmalar |
| `experiments/son-test-kilidi.json` | `splits.FINAL_TEST_LOCK_FILE` | yalnızca `run_final_test --final` yazar (`final_lock.write_lock_record`, bir kez); okuyucular `splits.require_lock_written` ister |
| `deliverables/tests/modeling/` (§2.6) | `deliverables/tests/unit/modeling/` | pytest `testpaths = tests/unit` |

## Bölmeler (§1)

| Plan | Kod |
|---|---|
| Eğitim | `TRAIN` (`"train"`) |
| Doğrulama-A (ayar) | `VAL_A` (`"val_a"`) |
| Doğrulama-B (kalibrasyon) | `VAL_B` (`"val_b"`) |
| Son test | `FINAL_TEST` (`"final_test"`) |
| K1..K4 (rolling-origin) | `ROLLING_FOLDS` (`Fold.name` = `"K1"`..`"K4"`, `fit`, `evaluation`, `core`) |
| geliştirme sınırı (FlightDate ≤ 2026-02-28) | `DEVELOPMENT_END`, `development_only`, `assert_no_final_test` |
| embargo (§1.4) | `TRAIN_EVAL_EMBARGO_DAYS` (= 0), `trim_end`, `check_temporal_order`, `conformal_calibration_window` |
| "bir kez bak" (§1.5) | `require_final_test_access`, `FinalTestAccessError` |

## Hedefler (§3)

| Plan | Kod |
|---|---|
| ArrDel15 | `targets.ARR_DEL15` = `"arr_del15"` |
| iptal | `targets.CANCELLED` = `"cancelled"` |
| varış rötarı (kantil) | `targets.ARR_DELAY` = `"arr_delay"` |
| aksaklik | `targets.DISRUPTION` = `"disruption"` |
| P50 / P80 / P95 | `QUANTILE_LEVELS`, sütun adları `q050`, `q080`, `q095` |

## Özellikler (§2.3)

| Plan adı | Kod adı |
|---|---|
| `crs_kalkis_saat`, `crs_kalkis_dk` | `crs_dep_hour`, `crs_dep_minute_of_day` |
| `crs_varis_saat` | `crs_arr_hour` |
| `saat_blogu` | `hour_block` (0..6) |
| `ay`, `haftanin_gunu`, `ayin_gunu`, `yilin_gunu` | `month`, `day_of_week`, `day_of_month`, `day_of_year` |
| `tatil_uzakligi_gun`, `tatil_haftasi` | `days_to_holiday`, `holiday_week` |
| `planli_kalkis_origin_saat`, `planli_varis_dest_saat`, `planli_kalkis_origin_gun` | `planned_departures_origin_hour`, `planned_arrivals_dest_hour`, `planned_departures_origin_day` |
| `mevsim` (B2) | `season` (0 = ara–şub, 1 = mar–may, 2 = haz–ağu, 3 = eyl–kas) |
| `te_rota_saat_arrdel15` | `te_route_hour_arrdel15` |
| `te_dest_saat_arrdel15` | `te_dest_hour_arrdel15` |
| `te_tasiyici_origin_arrdel15` | `te_carrier_origin_arrdel15` |
| `gecmis_rota_saat_p50/p80/p95` | `hist_route_hour_p50/p80/p95` |
| `te_rota_iptal` | `te_route_cancel` |
| `tarife_fazlasi_dk` | `schedule_excess_min` |
| `gecmis_taxiout_origin_saat_medyan` | `hist_taxiout_origin_hour_median` |
| `destek_n_*` | `support_n_*` |
| hava: `tavan_ft`, `ifr_bayrak`, `gozlem_yasi_dk` | `origin_/dest_` + `ceiling_ft`, `ifr_flag`, `obs_age_min` |
| hava: `wx_ts`, `wx_sn`, `wx_fzra`, `wx_ra`, `wx_fg` | aynı adlar, `origin_/dest_` önekli |
| `hava_eksik`, `dest_hava_var` | `*_weather_missing`, `dest_weather_available` |
| oracle hava | `oracle_` önekli aynı adlar (yalnızca `oracle=True`) |

## Sözleşme ve sınıflar (§2.2)

| Plan | Kod |
|---|---|
| `plan` / `T2` / `oracle` sözleşmesi | `features.build_contract("plan" \| "T2" \| "oracle", ...)` |
| `tarife` | `knowledge_time="schedule"` |
| `gecmis_gerceklesen` | `knowledge_time="past_realized"` |
| `gozlem_T_oncesi` | `knowledge_time="observation_before_T"` |
| `oracle` | `knowledge_time="oracle"` |
| `ufuk_saat`, `oracle_deneyi`, `bilgi_hazir_dk_once`, `kaynak='turetilmis'` | `horizon_hours`, `oracle_experiment`, `ready_minutes_before`, `source="derived"` |
| `dogrula_sutunlar` | `validate_columns` |

## §2.6 testleri

| Plan testi | Kod testi (`deliverables/tests/unit/modeling/`) |
|---|---|
| `test_ozellik_matrisi_yasak_yok` | `test_features.py::test_feature_matrix_has_no_forbidden_columns_and_contract_covers_all`, `::test_feature_code_rejects_frames_with_outcome_columns` |
| `test_sozlesme_tum_sutunlari_kapsar` | aynı test + `::test_undeclared_column_is_rejected_by_the_contract` |
| `test_hava_bilgi_zamani_satir_duzeyi` | `test_features.py::test_weather_row_level_information_time_is_enforced`, `::test_weather_exactly_at_the_cutoff_is_allowed` |
| `test_oracle_yalnizca_bayrakla` | `test_features.py::test_oracle_weather_is_off_by_default`, `::test_oracle_features_only_with_the_flag_and_labelled` |
| `test_istatistik_donemi` | `test_history.py::test_statistics_only_from_the_fit_window`, `test_features.py::test_history_features_fit_window_and_label_free_transform` |
| `test_transform_etiketsiz` | `test_history.py::test_transform_reads_no_labels`, `test_baselines.py::test_b1_ignores_evaluation_labels` |
| `test_bolme_ortusmez` | `test_splits.py::test_splits_do_not_overlap_and_are_ordered` |
| `test_gelistirme_test_gormez` | `test_splits.py::test_development_loader_never_returns_final_test_dates`, `test_run_baselines.py::test_run_writes_results_and_never_reads_the_final_test` |
| `test_hedef_tutarliligi` | `test_targets.py::test_arr_del15_consistency_counts_mismatches` (gerçek veride sayım `baseline-results.json` içinde) |
| embargo (§1.4) | `test_splits.py::test_embargo_trims_the_tail_of_the_fit_window`, `::test_check_temporal_order_rejects_overlap_and_embargo_violation`, `::test_conformal_window_has_a_one_day_embargo` |
| son test bayraksız açılmaz (§1.5) | `test_splits.py::test_final_test_is_refused_without_the_flag`, `::test_final_test_is_refused_once_the_lock_exists`, `test_run_baselines.py::test_loader_refuses_final_test_periods` |
| hedef kodlama yalnızca geçmişten (§2.4) | `test_history.py::test_out_of_fold_own_label_does_not_change_own_encoding`, `::test_expanding_encoding_uses_only_the_past` |
