Shorescan (c1, transect 40) vs TWL&CC best estimate
Created 2026-11-16 by compare_shorescan_twl.ipynb
Forecast file: Boston,_MA_1548_20241004-20250106_best_estimate.csv

Elevations m NAVD88; heights (R2, setup, swash) in m.
t_mid_*        middle of the capture (dt0 + n_valid / 2.0 Hz / 2)
fc_*           forecast interpolated to t_mid (fc_pp, fc_lead_hours: nearest hour)
clipped        runup at a transect limit (max exactly 0 or a repeated end value)
use            matched to a forecast and not clipped (rows in the statistics)
fc_swl         forecast tide + surge = tideWindSetup - setup
obs_twl        2% exceedance runup elevation (ss_twl_2pct_peaks)
obs_z2_series  cc_tide + ss_ru_2pct: 2% exceedance of the whole time series
obs_zmean      mean runup elevation (ss_twl_mean)
obs_R2         obs_twl - fc_swl      obs_setup  obs_zmean - fc_swl
obs_S          4 * std of runup elevation (significant swash)
obs_S_ss/_ig   Shorescan spectral sea-swell / infragravity swash (new CSV only)
err_*          forecast - observed
cc_* columns   forecast stored in the Shorescan files (old 00:00 UTC issue);
               datum-corrected in new-format CSVs, -0.082 m in old ones.
