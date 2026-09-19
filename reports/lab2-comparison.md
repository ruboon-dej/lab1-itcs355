# Lab 2 — Run comparison

Experiment `itcs355-lab2` · 12 trials · total Azure study spend approximately 2.91 THB

The 12 trials were completed on Azure ML managed compute. The available evidence provides total study spend, but not a verified billing amount for each individual job, so the cost-per-trial figure below is an average rather than per-job billing.

Average study cost per trial: **0.2425 THB**.

`thb_per_point` uses this average trial cost and therefore is a comparison indicator, not an individual Azure billing record.

| run_id                     |   val_roc_auc |   test_roc_auc |   n_estimators |   max_depth |   min_samples_leaf |   avg_cost_thb | thb_per_point   |
|:---------------------------|--------------:|---------------:|---------------:|------------:|-------------------:|---------------:|:----------------|
| great_moon_72n9b5dm4g      |        0.8426 |         0.8533 |            100 |           4 |                  5 |         0.2425 | 0.1503          |
| amiable_honey_8f8c1b6flt   |        0.8424 |         0.8518 |            100 |           4 |                  1 |         0.2425 | 0.1518          |
| good_head_b3nqq92cqp       |        0.8411 |         0.8545 |            300 |           4 |                  5 |         0.2425 | 0.1658          |
| keen_oil_0jzpdw142m        |        0.8404 |         0.8537 |            300 |           4 |                  1 |         0.2425 | 0.1743          |
| affable_napa_1t3680gjgd    |        0.8397 |         0.8466 |            100 |           8 |                  5 |         0.2425 | 0.1832          |
| ashy_ocean_dvpm1b8j71      |        0.8377 |         0.8491 |            300 |           8 |                  5 |         0.2425 | 0.2158          |
| affable_cassava_0ts068759l |        0.8354 |         0.8431 |            300 |          12 |                  5 |         0.2425 | 0.2722          |
| amiable_heart_0hbxn6sw4l   |        0.8338 |         0.8478 |            300 |           8 |                  1 |         0.2425 | 0.3315          |
| shy_nut_t1jftmfmc2         |        0.8322 |         0.8417 |            100 |          12 |                  5 |         0.2425 | 0.425           |
| keen_town_n71sc8024r       |        0.8312 |         0.8488 |            100 |           8 |                  1 |         0.2425 | 0.5131          |
| epic_stamp_tdqd5qntfs      |        0.8268 |         0.8415 |            100 |          12 |                  1 |         0.2425 | 6.5959          |
| bold_basket_zphkn345fm     |        0.8265 |         0.8374 |            300 |          12 |                  1 |         0.2425 | —               |

## Which model did you register, and why?

The registered configuration was `n_estimators=100`, `max_depth=4`, `min_samples_leaf=5`. It was not selected simply by taking the highest test score, because test data is held out from model selection. The 12-trial sweep identified this configuration as a strong validation candidate, and it was then rerun across seeds to examine stability. For seeds 20260101, 20260102, and 20260103, validation ROC-AUC was 0.8426, 0.8733, and approximately 0.8430 respectively, showing meaningful variation. The 20260102 run was selected based on validation performance, with test ROC-AUC reported only as held-out evidence. The complete 12-trial study cost approximately 2.91 THB, or about 0.24 THB per trial on average; one monthly retraining run would therefore be inexpensive at this observed scale. The choice could still be wrong because the seed also changes the generated dataset in these reruns, so the stability check is not a pure model-randomness test.

## Selection evidence

- Original sweep: 12 Azure ML trials.
- Selected configuration: `100 / 4 / 5`.
- Selection seed rerun: `20260102`.
- Selected run: `mango_boot_pbpr17lrhb`.
- Selected validation ROC-AUC: `0.8733`.
- Selected test ROC-AUC: `0.8463`.
- Three-seed validation ROC-AUC SD: approximately `0.018`.
- Total observed study spend: approximately `2.91 THB`.