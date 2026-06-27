[app]
title = GATI Route Manager
package.name = gati
package.domain = org.gati
source.dir = .
source.main = main_kivy.py
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy>=2.3.0,plyer>=2.1,pdfplumber>=0.11,folium>=0.18,geopy>=2.4
orientation = portrait
osx.python_version = 3
osx.kivy_version = 2.3.0
fullscreen = 1
android.api = 34
android.minapi = 21
android.ndk = 27
android.sdk = 34
android.gradle_dependencies = 
android.add_src = 
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.arch = arm64-v8a
android.allow_backup = True
android.wakelock = False
android.library_references = 

[buildozer]
log_level = 2
warn_on_root = 1

[update]
