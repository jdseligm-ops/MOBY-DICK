// OBD 17 kt inner detector (lengths in mm; size_z is the HALF height).
// Dimensions: OHN24 (T. Ohno, Tohoku M.S. thesis 2024) Table 5.1 p.44; tank-liner optics ONO25 p.104.
//   SS tank     r 15.016 / 15.000 m, h 50.032 / 50.000 m      (outer / inner)
//   buffer      K-290 oil between tank and acrylic
//   acrylic     r 12.05 / 12.00 m,  h 44.1 / 44.0 m           -> 5 cm wall
//   LS          r 12 m, h 44 m: LAB + 3 g/L PPO + 0.1 wt% 6Li  (19,900 m3, 17.8 kt at 0.892 g/cm3)
//   PMTs        12,505 x 20-inch in glass shields on the tank wall (layout: tools/make_pmt_layout.py)
// Not modelled: outer-detector PMTs (3850, outside the tank), acrylic support pillars, fill ports, cabling.

{
"name": "GEO",
"index": "world",
"run_range": [0, 0],
"mother": "",
"type": "tube",
"r_max": 17000.0,
"size_z": 27000.0,
"material": "salt_water",
"invisible": 1,
}

{
"name": "GEO",
"index": "ss_tank",
"run_range": [0, 0],
"mother": "world",
"type": "tube",
"r_max": 15016.0,
"size_z": 25016.0,
"material": "stainless_steel",
"color": [0.6, 0.6, 0.6, 0.1],
}

// 1 mm black liner on the tank inner surface: reflectivity ~0 as in ONO25's optics model (p.104)
{
"name": "GEO",
"index": "black_liner",
"run_range": [0, 0],
"mother": "ss_tank",
"type": "tube",
"r_max": 15000.0,
"size_z": 25000.0,
"material": "acrylic_black",
"color": [0.1, 0.1, 0.1, 0.1],
}

{
"name": "GEO",
"index": "buffer",
"run_range": [0, 0],
"mother": "black_liner",
"type": "tube",
"r_max": 14999.0,
"size_z": 24999.0,
"material": "obd_k290",
"color": [0.9, 0.8, 0.3, 0.05],
}

{
"name": "GEO",
"index": "acrylic_vessel",
"run_range": [0, 0],
"mother": "buffer",
"type": "tube",
"r_max": 12050.0,
"size_z": 22050.0,
"material": "obd_acrylic",
"color": [0.4, 0.7, 1.0, 0.2],
}

{
"name": "GEO",
"index": "scintillator",
"run_range": [0, 0],
"mother": "acrylic_vessel",
"type": "tube",
"r_max": 12000.0,
"size_z": 22000.0,
"material": "obd_ls_li6",
"color": [0.2, 1.0, 0.4, 0.1],
}

{
"name": "GEO",
"index": "inner_pmts",
"run_range": [0, 0],
"mother": "buffer",
"type": "pmtarray",
"pmt_model": "obd_r3600",
"pmt_detector_type": "idpmt",
"sensitive_detector": "/mydet/pmt/inner",
"pos_table": "PMTINFO_OBD17kt",
"orientation": "manual",
"encapsulation": 1,
"encapsulation_model": "OBD_GLASS_SHIELD",
}
