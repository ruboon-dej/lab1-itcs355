# Lab 2 — Run comparison

Experiment `itcs355-lab2` · 12 trials · total study spend 2.91 THB

The 12 trials were completed on Azure ML managed compute. The available evidence provides total study spend, but not a verified billing amount for each individual job, so the cost-per-trial figure below is an average rather than per-job billing.

| run_id                     | val_roc_auc | test_roc_auc | n_estimators | max_depth | min_samples_leaf |
| :------------------------- | ----------: | -----------: | -----------: | --------: | ---------------: |
| amiable_honey_8f8c1b6flt   |      0.8424 |       0.8518 |          100 |         4 |                1 |
| great_moon_72n9b5dm4g      |      0.8426 |       0.8533 |          100 |         4 |                5 |
| keen_town_n71sc8024r       |      0.8312 |       0.8488 |          100 |         8 |                1 |
| affable_napa_1t3680gjgd    |      0.8397 |       0.8466 |          100 |         8 |                5 |
| epic_stamp_tdqd5qntfs      |      0.8268 |       0.8415 |          100 |        12 |                1 |
| shy_nut_t1jftmfmc2         |      0.8322 |       0.8417 |          100 |        12 |                5 |
| keen_oil_0jzpdw142m        |      0.8404 |       0.8537 |          300 |         4 |                1 |
| good_head_b3nqq92cqp       |      0.8411 |       0.8545 |          300 |         4 |                5 |
| amiable_heart_0hbxn6sw4l   |      0.8338 |       0.8478 |          300 |         8 |                1 |
| ashy_ocean_dvpm1b8j71      |      0.8377 |       0.8491 |          300 |         8 |                5 |
| bold_basket_zphkn345fm     |      0.8265 |       0.8374 |          300 |        12 |                1 |
| affable_cassava_0ts068759l |      0.8354 |       0.8431 |          300 |        12 |                5 |

## Which model did you register, and why?

The selected configuration was `n_estimators=100`, `max_depth=4`,
`min_samples_leaf=5`. In the 12-trial sweep it had the highest validation
ROC-AUC at 0.8426, although the margin over the next configuration was very
small (0.0002). The registered model uses seed 20260102.

The same configuration was rerun with seeds 20260101, 20260102, and 20260103,
giving validation ROC-AUC values of 0.8426, 0.8733, and 0.8430 respectively.
The standard deviation is approximately 0.018. However, the seed is also used
when generating the dataset, so this variation reflects both data and model
randomness rather than model randomness alone.

The 12-run study cost 2.91 THB in total, or approximately 0.24 THB per trial
as an average. One monthly retrain is about 0.24 THB by that average, an
estimate rather than a verified Azure bill.

One way the selection could be wrong is that the small validation margin
between the top configurations is much smaller than the variation observed
across the seed reruns. A more controlled comparison would keep the dataset
fixed while varying only the model seed.