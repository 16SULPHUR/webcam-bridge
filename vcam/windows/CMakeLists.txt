# Webcam Bridge virtual camera (DirectShow) — built from vendored softcam.
#
#   cmake -S vcam/windows -B build/vcam-x64 -A x64
#   cmake --build build/vcam-x64 --config Release
#
# Produces webcam_bridge_cam.dll. Build once with -A x64 and once with
# -A Win32 so both 64-bit and 32-bit camera apps can see the device.

cmake_minimum_required(VERSION 3.20)
project(webcam_bridge_cam LANGUAGES CXX)

if(NOT MSVC)
  message(FATAL_ERROR "The virtual camera DLL must be built with MSVC (Visual Studio 2019+).")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# Static CRT: the DLL is loaded into third-party apps (Zoom, Teams, ...), so it
# must not depend on a Visual C++ redistributable being installed.
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

set(SOFTCAM ${CMAKE_CURRENT_SOURCE_DIR}/third_party/softcam/src)

add_compile_definitions(WIN32 UNICODE _UNICODE _CRT_SECURE_NO_WARNINGS $<$<NOT:$<CONFIG:Debug>>:NDEBUG>)
add_compile_options(/MP /sdl)

add_library(baseclasses STATIC
  ${SOFTCAM}/baseclasses/amfilter.cpp
  ${SOFTCAM}/baseclasses/amvideo.cpp
  ${SOFTCAM}/baseclasses/combase.cpp
  ${SOFTCAM}/baseclasses/dllentry.cpp
  ${SOFTCAM}/baseclasses/dllsetup.cpp
  ${SOFTCAM}/baseclasses/mtype.cpp
  ${SOFTCAM}/baseclasses/source.cpp
  ${SOFTCAM}/baseclasses/winutil.cpp
  ${SOFTCAM}/baseclasses/wxdebug.cpp
  ${SOFTCAM}/baseclasses/wxlist.cpp
  ${SOFTCAM}/baseclasses/wxutil.cpp
)
target_compile_definitions(baseclasses PRIVATE _LIB)
# Microsoft's BaseClasses predate standard conformance mode; softcam builds them with /W3 only.
target_compile_options(baseclasses PRIVATE /W3)
target_include_directories(baseclasses PUBLIC ${SOFTCAM}/baseclasses)

add_library(softcamcore STATIC
  ${SOFTCAM}/softcamcore/DShowSoftcam.cpp
  ${SOFTCAM}/softcamcore/FrameBuffer.cpp
  ${SOFTCAM}/softcamcore/Misc.cpp
  ${SOFTCAM}/softcamcore/SenderAPI.cpp
  ${SOFTCAM}/softcamcore/Watchdog.cpp
)
target_include_directories(softcamcore PUBLIC ${SOFTCAM} ${SOFTCAM}/softcamcore)
target_link_libraries(softcamcore PUBLIC baseclasses)
target_compile_options(softcamcore PRIVATE /W4 /permissive-)

add_library(webcam_bridge_cam SHARED
  ${SOFTCAM}/softcam/softcam.cpp
  ${SOFTCAM}/softcam/softcam.def
)
target_include_directories(webcam_bridge_cam PRIVATE ${SOFTCAM}/softcam)
target_compile_options(webcam_bridge_cam PRIVATE /W4 /permissive-)
target_link_libraries(webcam_bridge_cam PRIVATE
  softcamcore strmiids winmm ole32 oleaut32 uuid advapi32 user32 gdi32)

install(TARGETS webcam_bridge_cam RUNTIME DESTINATION .)
