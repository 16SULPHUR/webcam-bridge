#include "softcam.h"

#include <olectl.h>
#include <initguid.h>

#include <softcamcore/DShowSoftcam.h>
#include <softcamcore/SenderAPI.h>


// {F23C4002-953E-4221-AD81-B03CB81F72B2}  [webcam-bridge: own CLSID so we never collide with other softcam users]
DEFINE_GUID(CLSID_DShowSoftcam,
0xf23c4002, 0x953e, 0x4221, 0xad, 0x81, 0xb0, 0x3c, 0xb8, 0x1f, 0x72, 0xb2);


namespace {

// Setup data

const wchar_t FILTER_NAME[] = L"Webcam Bridge";  // [webcam-bridge] device name shown in apps
const GUID &FILTER_CLASSID = CLSID_DShowSoftcam;

const AMOVIESETUP_MEDIATYPE s_pin_types[] =
{
    {
        &MEDIATYPE_Video,       // Major type
        &MEDIASUBTYPE_NULL      // Minor type
    }
};

const AMOVIESETUP_PIN s_pins[] =
{
    {
        const_cast<LPWSTR>(L"Output"),  // Pin string name
        FALSE,                  // Is it rendered
        TRUE,                   // Is it an output
        FALSE,                  // Can we have none
        FALSE,                  // Can we have many
        &CLSID_NULL,            // Connects to filter
        NULL,                   // Connects to pin
        1,                      // Number of types
        s_pin_types             // Pin details
    }
};

const REGFILTER2 s_reg_filter2 =
{
    1,
    MERIT_DO_NOT_USE,
    1,
    s_pins
};

CUnknown * WINAPI CreateSoftcamInstance(LPUNKNOWN lpunk, HRESULT *phr)
{
    return softcam::Softcam::CreateInstance(lpunk, FILTER_CLASSID, phr);
}

} // namespace

// COM global table of objects in this dll

CFactoryTemplate g_Templates[] =
{
    {
        FILTER_NAME,
        &FILTER_CLASSID,
        &CreateSoftcamInstance,
        NULL,
        nullptr
    }
};
int g_cTemplates = sizeof(g_Templates) / sizeof(g_Templates[0]);


STDAPI DllRegisterServer()
{
    HRESULT hr = AMovieDllRegisterServer2(TRUE);
    if (FAILED(hr))
    {
        return hr;
    }
    hr = CoInitialize(nullptr);
    if (FAILED(hr))
    {
        return hr;
    }
    do
    {
        IFilterMapper2 *pFM2 = nullptr;
        hr = CoCreateInstance(
                CLSID_FilterMapper2, nullptr, CLSCTX_INPROC_SERVER,
                IID_IFilterMapper2, (void**)&pFM2);
        if (FAILED(hr))
        {
            break;
        }
        pFM2->UnregisterFilter(
                &CLSID_VideoInputDeviceCategory,
                0,
                FILTER_CLASSID);
        hr = pFM2->RegisterFilter(
                FILTER_CLASSID,
                FILTER_NAME,
                0,
                &CLSID_VideoInputDeviceCategory,
                FILTER_NAME,
                &s_reg_filter2);
        pFM2->Release();
    } while (0);
    CoFreeUnusedLibraries();
    CoUninitialize();
    return hr;
}

STDAPI DllUnregisterServer()
{
    HRESULT hr = AMovieDllRegisterServer2(FALSE);
    if (FAILED(hr))
    {
        return hr;
    }
    hr = CoInitialize(nullptr);
    if (FAILED(hr))
    {
        return hr;
    }
    do
    {
        IFilterMapper2 *pFM2 = nullptr;
        hr = CoCreateInstance(
                CLSID_FilterMapper2, nullptr, CLSCTX_INPROC_SERVER,
                IID_IFilterMapper2, (void**)&pFM2);
        if (FAILED(hr))
        {
            break;
        }
        hr = pFM2->UnregisterFilter(
                &CLSID_VideoInputDeviceCategory,
                FILTER_NAME,
                FILTER_CLASSID);
        pFM2->Release();
    } while (0);
    CoFreeUnusedLibraries();
    CoUninitialize();
    return hr;
}

extern "C" BOOL WINAPI DllEntryPoint(HINSTANCE, ULONG, LPVOID);

BOOL APIENTRY DllMain(HANDLE hModule, DWORD  dwReason, LPVOID lpReserved)
{
    return DllEntryPoint((HINSTANCE)(hModule), dwReason, lpReserved);
}


//
// Softcam Sender API
//

extern "C" scCamera scCreateCamera(int width, int height, float framerate)
{
    return softcam::sender::CreateCamera(width, height, framerate);
}

extern "C" void     scDeleteCamera(scCamera camera)
{
    return softcam::sender::DeleteCamera(camera);
}

extern "C" void     scSendFrame(scCamera camera, const void* image_bits)
{
    return softcam::sender::SendFrame(camera, image_bits);
}

extern "C" bool     scWaitForConnection(scCamera camera, float timeout)
{
    return softcam::sender::WaitForConnection(camera, timeout);
}

extern "C" bool     scIsConnected(scCamera camera)
{
    return softcam::sender::IsConnected(camera);
}
