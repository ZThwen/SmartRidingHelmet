由于使用本地依赖(aar文件导入), 部分开源库未关联导入, 故需补充以下远程依赖, 在/app/build.gradle文件中, 添加以下内容:

```groovy
dependencies {
    implementation "com.google.code.gson:gson:2.9.1"
    implementation "com.kyleduo.switchbutton:library:2.1.0"
    implementation "com.airbnb.android:lottie:6.0.0"
    implementation "io.github.cymchad:BaseRecyclerViewAdapterHelper:3.0.8"
    implementation "org.greenrobot:eventbus:3.3.1"
    implementation "com.squareup.okhttp3:okhttp:4.10.0"
    implementation "com.guolindev.permissionx:permissionx:1.6.4"
    implementation "com.github.bumptech.glide:glide:4.11.0"
    implementation "com.tencent:mmkv:1.2.14"
    implementation "com.tencent.mars:mars-xlog:1.2.6"
    implementation "com.github.hufeiyang.Android-AppLifecycleMgr:applifecycle-api:1.0.4"
}
```