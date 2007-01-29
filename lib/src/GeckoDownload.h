#ifndef __GECKO_DOWNLOAD_H__
#define __GECKO_DOWNLOAD_H__

#include <nsCOMPtr.h>
#include <nsIInterfaceRequestor.h>
#include <nsITransfer.h>
#include <nsIWebProgressListener.h>
#include <nsIMIMEInfo.h>
#include <nsIURL.h>
#include <nsILocalFile.h>
#include <nsStringAPI.h>

#define GECKODOWNLOAD_CID							 \
{ /* b1813bbe-6518-11db-967e-00e08161165f */         \
	0xb1813bbe,                                      \
	0x6518,                                          \
	0x11db,                                          \
	{0x96, 0x7e, 0x0, 0xe0, 0x81, 0x61, 0x16, 0x5f} \
}

class nsIFactory;

extern "C" NS_EXPORT nsresult NS_NewGeckoDownloadFactory(nsIFactory** aFactory);

#endif // __GECKO_DOWNLOAD_H__
