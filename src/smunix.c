/*------------------------------------------------------------*/
/* Copyright ACULAB plc. (c) 1996-1997                        */
/*------------------------------------------------------------*/
/*                                                            */
/*                                                            */
/* Program File Name : smunix.c                               */
/*                                                            */
/*           Purpose : SHARC module driver library            */
/*                     (UNIX specific)                        */
/*                                                            */
/*            Author : Peter Dain                             */
/*                                                            */
/*       Create Date : 21st February 1997                     */
/*                                                            */
/*                                                            */					    
/*                                                            */
/*                                                            */
/*------------------------------------------------------------*/
/*                                                            */
/*                                                            */
/* Change History                                             */
/*                                                            */
/* cur:  1.00   21/01/97    pgd   First issue                 */
/* rev:  1.00   21/01/97    pgd   First issue                 */
/*                                                            */
/*------------------------------------------------------------*/

/*
 * The Pre-processer definition UNIX_SYSTEM should be defined for Unix Prosody applications.
 * The following Unix variants are provided for through conditional compilation:
 *      SM_POLL_UNIX  - Unix supporting chpoll driver entry point and Prosody events through poll system call
 *					    for example Unixware 2
 *      SM_SEL_UNIX   - Unix supporting driver "select" primitives and Prosody events through select system call
 *      SM_CLONE_UNIX - Unix supporting clone node channels and Prosody events through i/o on clone channels
 *
 * In addition if multi-threaded applications are being written, SM_THREAD_UNIX, should also be defined. 
 *
 * if no header with correct open/clode/ioctl prototypes define SM_INC_DEVINTF
 *
 */
#include "smdrvr.h"
#include "smosintf.h"


#ifdef SM_THREAD_UNIX 
#ifndef __linux__
#ifdef SM_POLL_UNIX 
#define SM_UW_MUTEX_UNIX
#endif
#ifdef SM_CLONE_UNIX 
#define SM_UW_MUTEX_UNIX
#endif
#endif
#endif

#ifdef SM_UW_MUTEX_UNIX
#define tSMDMutexType 		mutex_t
#define smd_mutex_init		mutex_init
#define smd_mutex_destroy	mutex_destroy
#define smd_mutex_lock		mutex_lock
#define smd_mutex_unlock	mutex_unlock
#else
#define tSMDMutexType 		pthread_mutex_t
#define smd_mutex_init		pthread_mutex_init
#define smd_mutex_destroy	pthread_mutex_destroy
#define smd_mutex_lock		pthread_mutex_lock
#define smd_mutex_unlock	pthread_mutex_unlock
#endif

#include <string.h>
#include <ctype.h>
#include <stdlib.h>
#include <fcntl.h>
#include <stdio.h>
#include <errno.h>
#include <unistd.h>

#ifdef SM_THREAD_UNIX 
#ifdef SM_UW_MUTEX_UNIX
#include <synch.h>
#else
#include <pthread.h>
#endif
#endif

#include <sys/types.h>
#include <sys/times.h>
#ifdef SM_SEL_UNIX 
#include <sys/select.h>
#endif
#ifdef SM_POLL_UNIX 
#include <sys/poll.h>
#endif

#ifdef SM_CLONE_UNIX
#include <aio.h>
#endif

#define kSMUNIXControlDev -2

#ifdef SM_INC_DEVINTF 

int open(
#ifdef __STDC__
	const char*, int, ...
#endif
);

int  close (
#ifdef __STDC__
 	int 
#endif
);

int  ioctl ( 
#ifdef __STDC__
	int, int, SMMSGBLK * 
#endif
);

#endif

int smopened 			= 0;
int smdControlDevHandle = kSMNullDevHandle;

char smdevname[] = { "/dev/mvsm0" };

/*****************************************************************************************/
/****************** Generic code common to all Unix variants *****************************/
/*****************************************************************************************/

/*
 * SMD_OPEN_CTL_DEV
 *
 * Open master (control) device for driver.
 * Handle for this device is stored in global:
 * 
 *         smdControlDevHandle
 *
 * and is used for IOCTL interactions etc. 
 */
tSMDevHandle smd_open_ctl_dev( void )
{
	int result;

	if (smopened == 0)
	{
		smdControlDevHandle = open(smdevname,O_RDONLY);

		if (smdControlDevHandle < 0)
		{
		}
		else
		{
			smopened = 1;
		}
	}

	result = (smopened) ? kSMUNIXControlDev : kSMNullDevHandle;

	return result;
}


#ifdef SM_CLONE_UNIX

/*
 * SMD_OPEN_CHNL_DEV
 *
 * Allocate an O/S handle for a specific channel whose
 * integer index 1..n + is supplied as channel in bits 0..11,
 * clone device no. is in bits 12..15.
 */
tSMDevHandle smd_open_chnl_dev( tSMChannelId channel )
{
	char			channelDeviceName[20];
	tSMChannelId 	result;
	tSM_INT			handle;
	SMMSGBLK		smmsgblk;

	/*
	 * In order to use NT read/write facilities,
	 * translate returned channel to a logical device name,
	 * and open that device.
	 *
	 * For the user, the channel id is identified with 
	 * this new handle.
	 */
	sprintf(	&channelDeviceName[0],
				"/dev/smcl%d",
				(((int)(channel>>12)&0x0f))	);

	handle = open(&channelDeviceName[0],O_RDWR);

	if (handle < 0)
	{
		result = kSMNullDevHandle;
	}
	else
	{
		result = (tSMChannelId) handle;

	   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdBindToCCB;
	   	smmsgblk.length			= 0;
	   	smmsgblk.command		= 0;
	   	smmsgblk.module			= -1;
	   	smmsgblk.apiLibVersion 	= ((kSMDVersionMaj<<8) + kSMDVersionMin);
	   	smmsgblk.fwLibVersion  	= -1;	
	   	smmsgblk.error   		= 0;
		smmsgblk.ioctlup		= 0;
		smmsgblk.channel        = channel;

		ioctl(handle,kSMDrvrCtlCmdBindToCCB,&smmsgblk);
	}

	return result;
}

#else

/*
 * SMD_OPEN_CHNL_DEV
 *
 * Allocate an O/S handle for a specific channel whose
 * integer index 1..n is supplied as channel.
 */
tSMDevHandle smd_open_chnl_dev( tSMChannelId channel )
{
	char			channelDeviceName[20];
	tSMChannelId 	result;
	tSM_INT			handle;

	strcpy(&channelDeviceName[0],"/dev/mvsm");

	sprintf(	&channelDeviceName[strlen(&channelDeviceName[0])],
				"%03d",
				(((int)(channel)))									);

	handle = open(&channelDeviceName[0],O_RDWR+O_NONBLOCK);

	if (handle < 0)
	{
		result = kSMNullDevHandle;
	}
	else
	{
		result = (tSMChannelId) handle;
	}

	return result;
}

#endif


/*
 * SMD_CLOSE_CHNL_DEV
 *
 * Release a previously allocated handle for a channel.
 */
void smd_close_chnl_dev( tSMDevHandle handle )
{
	if (handle != kSMNullDevHandle)	 
	{
		close(handle);
 	}
}


int smd_ioctl_ctl_dev( int func, SMMSGBLK* psmmsgblk )
{
	int			 rc;
	tSMDevHandle smControlDevice;

	rc = -1;

	smControlDevice = smd_open_ctl_dev( );

	if (smControlDevice != kSMNullDevHandle)
	{
		rc = ioctl(smdControlDevHandle,func,psmmsgblk);
	}

	return rc;
}


/* 
 * SMD_IOCTL_DEV_GENERIC 
 *
 * Invoke IOCTL request to control driver.
 */
int  smd_ioctl_dev_generic( tSM_INT function, SMIOCTLU* pioctl, tSMDevHandle smh, tSM_INT size )
{
	SMMSGBLK smmsgblk;

   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdIOCTL;
   	smmsgblk.length			= size;
   	smmsgblk.command		= function;
   	smmsgblk.module			= -1;										/* Module specific only if f/w specific API call*/
   	smmsgblk.apiLibVersion 	= ((kSMDVersionMaj<<8) + kSMDVersionMin);
   	smmsgblk.fwLibVersion  	= -1;										/* Inducates generic API call. */
   	smmsgblk.error   		= 0;
	smmsgblk.ioctlup		= pioctl;
	smmsgblk.channel        = (smh == kSMUNIXControlDev) ? kSMNullChannelId : smh;

	if (smh == kSMUNIXControlDev)
	{
		if (ioctl(smdControlDevHandle,(int)function,&smmsgblk) == -1)
		{
			smmsgblk.error = ERR_SM_DEVERR;
		}
	}
	else
	{
		if (ioctl(smh,(int)function,&smmsgblk) == -1)
		{
			smmsgblk.error = ERR_SM_DEVERR;
		}
	}

	return(smmsgblk.error);
}


/* 
 * SMD_IOCTL_FWAPI 
 *
 * Invoke f/w specific IOCTL request to control driver.
 */
int smd_ioctl_dev_fwapi( tSM_INT function, SMIOCTLU * pioctl, tSMDevHandle smh, tSM_INT size, tSM_INT module, tSM_INT fwVersion )
{
	int 		result;
	int  		bytesReturned;
	SMMSGBLK 	smmsgblk;

   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdIOCTL;
   	smmsgblk.length			= size;
   	smmsgblk.command		= function;
   	smmsgblk.module			= module;
   	smmsgblk.apiLibVersion  = ((kSMDVersionMaj<<8) + kSMDVersionMin);
   	smmsgblk.fwLibVersion   = fwVersion;
   	smmsgblk.error   		= 0;
	smmsgblk.ioctlup		= pioctl;
	smmsgblk.channel        = (smh == kSMUNIXControlDev) ? kSMNullChannelId : smh;

	if (smh == kSMUNIXControlDev)
	{
		if (ioctl(smdControlDevHandle,(int)function,&smmsgblk) == -1)
		{
			smmsgblk.error = ERR_SM_DEVERR;
		}
	}
	else
	{
		if (ioctl(smh,(int)function,&smmsgblk) == -1)
		{
			smmsgblk.error = ERR_SM_DEVERR;
		}
	}

	return(smmsgblk.error);
}


/* 
 * SMD_READ_DEV 
 *
 * Invoke read request to driver.
 */
int  smd_read_dev( tSMChannelId smh, char* data, tSM_INT* length )
{
	int rc;
	int result;

	result = 0;

	rc = read(smh,(void*)data,(size_t)(*length));

	if (rc == -1)
	{
		if (errno == EAGAIN)
		{
			result = 0;

			*length = 0;
		}
		else
		{
			result = ERR_SM_DEVERR;
		}
	}
	else
	{
		*length = rc;
	}

	return result;
}


/* 
 * SMD_WRITE_DEV 
 *
 * Invoke write request to control driver.
 */
int  smd_write_dev( tSMChannelId smh, char* data, tSM_INT length )
{
	int rc;
	int result;

	result = 0;

	rc = write(smh,(void*)data,(size_t)length);

	if (rc == -1)
	{
		result = ERR_SM_DEVERR;
	}
	else if (rc < length)
	{
		result = ERR_SM_NO_CAPACITY;
	}

	return result;
}


/*
 * SMD_FILE_OPEN
 *
 * Open a file for firmware download.
 */
tSMFileHandle smd_file_open( char* fnamep )
{
	return open(fnamep,O_RDONLY);
}


/*
 * SMD_FILE_READ
 *
 * Read data for firmware download.
 */
int smd_file_read(	tSMFileHandle fh, char* buffp, tSM_INT len )
{
	return read(fh,buffp,len);
}


/*
 * SMD_FILE_CLOSE
 *
 * Close file after firmware download completed.
 */
int smd_file_close( tSMFileHandle fh )
{
	return close(fh);  
}


/*
 * SMD_YIELD
 *
 * Yield context to another thread or process.
 */
int smd_yield( void )
{
#ifdef SM_UW_MUTEX_UNIX
	thr_yield();
#else
	sched_yield();
#endif
	return 0;
}


/*
 * SMD_INITIALIZE_CRITICAL_SECTION
 *
 * Used in high level conferencing library only.
 */
int smd_initialize_critical_section( tSMCriticalSection* csect )
{
	int		 result;
	tSMDMutexType* criticalSectionMutex;

	result = 0;

	*csect = 0;

	criticalSectionMutex = malloc(sizeof(tSMDMutexType));

	if (criticalSectionMutex != 0)
	{
#ifdef SM_UW_MUTEX_UNIX
		if (smd_mutex_init(criticalSectionMutex,USYNC_THREAD,NULL) == 0)
#else
		if (smd_mutex_init(criticalSectionMutex,NULL) == 0)
#endif
		{
			*csect = (tSMCriticalSection) criticalSectionMutex;
		}
		else
		{
			free((void*)criticalSectionMutex);

			result = ERR_SM_NO_RESOURCES;
		}
	}
	else
	{
		result = ERR_SM_NO_RESOURCES;
	}

	return result;
}


/*
 * SMD_DELETE_CRITICAL_SECTION
 *
 * Used in high level conferencing library only.
 */
int smd_delete_critical_section( tSMCriticalSection* csect )
{
	if (*csect != 0)
	{
		smd_mutex_destroy((tSMDMutexType*)(*csect));

		free(*csect);
	}

	return 0;
}


/*
 * SMD_ENTER_CRITICAL_SECTION
 *
 * Used in high level conferencing library only.
 */
int smd_enter_critical_section( tSMCriticalSection* csect )
{
	smd_mutex_lock((tSMDMutexType*)(*csect));

	return 0;
}


/*
 * SMD_LEAVE_CRITICAL_SECTION
 *
 * Used in high level conferencing library only.
 */
int smd_leave_critical_section( tSMCriticalSection* csect )
{
	smd_mutex_unlock((tSMDMutexType*)(*csect));

	return 0;
}




/*****************************************************************************************/
/****************** Event implementation using SELECT mechanism **************************/
/*****************************************************************************************/

#ifdef SM_SEL_UNIX 

#define SELREAD		0x01
#define SELWRITE	0x02
#define SELEXCEPT	0x04

int smd_ev_create( tSMEventId* eventId, tSMChannelId channelId, int eventKind, int eventScope )
{
	int			rc;
	tSMEventId 	ev;
	char		eventName[64];

	rc = 0;

	smd_open_ctl_dev();

	if ((eventKind == kSMEventTypeWriteData) || (eventKind == kSMEventTypeReadData))
	{
		if (eventScope == kSMChannelSpecificEvent)
		{
			eventId->fd   = (int) channelId;
		}
		else
		{
			eventId->fd   = (int) smdControlDevHandle;
		}

		eventId->mode = (eventKind == kSMEventTypeWriteData) ? SELWRITE : SELREAD;
	}
	else if (eventKind == kSMEventTypeRecog)
	{
		if (eventScope == kSMChannelSpecificEvent)
		{
			eventId->fd   = (int) channelId;
		}
		else
		{
			eventId->fd   = (int) smdControlDevHandle;
		}
		eventId->mode = SELEXCEPT;
	}
	else
	{
		rc = ERR_SM_NO_RESOURCES;
	}

	return rc;
}


int smd_ev_free( tSMEventId eventId )
{
	return 0;
}


int smd_ev_wait( tSMEventId eventId )
{
	int		result;
	int		rc;
	fd_set 	read_fds;
	fd_set 	write_fds;
	fd_set 	except_fds;
	fd_set* p;
	fd_set* q;
	fd_set* r;

	p = NULL;
	q = NULL;
	r = NULL;

	switch(eventId.mode)
	{
		case SELREAD:
			p = &read_fds;
			FD_ZERO(p);
			FD_SET(eventId.fd,&read_fds);
			break;

		case SELWRITE:
			q = &write_fds;
			FD_ZERO(q);
			FD_SET(eventId.fd,q);
			break;

		case SELEXCEPT:
			r = &except_fds;
			FD_ZERO(r);
			FD_SET(eventId.fd,r);
			break;
	}

	rc = select(FD_SETSIZE,p,q,r,0);

	result = 0;

	if (rc < 0)
	{
		if (errno == EINTR)
		{
			result = ERR_SM_OS_INTERRUPTED_WAIT;
		}
		else if (rc != 0)
		{
			result = ERR_SM_DEVERR;
		}
	}

	return result;
}



/*
 * Returns < 0 if error, 0 if nothing was aborted else count of aborts.
 */
int smd_ev_abort( int evKind, int evScope, int channelIx )
{
	int				result;
	int				rc;
	tSMDevHandle 	smControlDevice;
	SMMSGBLK		smmsgblk;

	result = 0;

	smControlDevice = smd_open_ctl_dev( );

	if (smControlDevice != kSMNullDevHandle)
	{
		/*
		 * Abort any uncompleted event waits.
		 */
	   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdAbortEventWait;
	   	smmsgblk.length			= 0;
	   	smmsgblk.command		= evKind;
	   	smmsgblk.module			= -1;
	   	smmsgblk.apiLibVersion 	= ((kSMDVersionMaj<<8) + kSMDVersionMin);
	   	smmsgblk.fwLibVersion  	= -1;	
	   	smmsgblk.error   		= 0;
		smmsgblk.ioctlup		= 0;
		smmsgblk.channel        = (evScope == kSMChannelSpecificEvent) ? channelIx : -1;

		rc = ioctl((int)smdControlDevHandle,kSMDrvrCtlCmdAbortEventWait,&smmsgblk);

		if (rc < 0)
		{
			result = ERR_SM_DEVERR;
		}
		else if (smmsgblk.error != 0)
		{
			result = smmsgblk.error;
		}
	}
	else
	{
		result = ERR_SM_DEVERR;
	}

	return result;
}


#endif

/*****************************************************************************************/
/****************** Event implementation using cloned channels mechanism *****************/
/*****************************************************************************************/

#ifdef SM_CLONE_UNIX

int smd_ioctl_ev_wait( tSMEventId eventId )
{
	int				result;
	int				rc;
	tSMDevHandle 	smControlDevice;
	SMMSGBLK		smmsgblk;

	result = 0;

   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdIOCTLEventWait;
   	smmsgblk.length			= 0;
   	smmsgblk.command		= 0;
   	smmsgblk.module			= -1;
   	smmsgblk.apiLibVersion 	= ((kSMDVersionMaj<<8) + kSMDVersionMin);
   	smmsgblk.fwLibVersion  	= -1;	
   	smmsgblk.error   		= 0;
	smmsgblk.ioctlup		= 0;
	smmsgblk.channel        = 0;

	rc = ioctl((int)eventId,kSMDrvrCtlCmdIOCTLEventWait,&smmsgblk);

	if (rc < 0)
	{
		if (errno == EINTR)
		{
			result = ERR_SM_OS_INTERRUPTED_WAIT;
		}
		else
		{
			result = ERR_SM_DEVERR;
		}
	}
	else
	{
		result = smmsgblk.error;
	}

	return result;
}


static int smd_ev_open_and_bind(tSMEventId* eventId, int dacpDev, int eventKind, tSMChannelId smdCardAndChannelId )
{
	int				result;
	char			channelDeviceName[20];
	tSM_INT			handle;
	SMMSGBLK		smmsgblk;
	int				rc;

	result = 0;

	sprintf(&channelDeviceName[0],"/dev/smcl%d",dacpDev);

	/*
	 * Create a clone channel for the event.
	 */
	handle = open(&channelDeviceName[0],O_RDWR);

	if (handle >= 0)
	{
		/*
		 * Bind the new clone channel (which the driver does not
		 * yet know what it is for) to an event for the channel.
		 */
	   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdBindToEvent;
	   	smmsgblk.length			= 0;
	   	smmsgblk.command		= eventKind;
	   	smmsgblk.module			= -1;
	   	smmsgblk.apiLibVersion 	= ((kSMDVersionMaj<<8) + kSMDVersionMin);
	   	smmsgblk.fwLibVersion  	= -1;	
	   	smmsgblk.error   		= 0;
		smmsgblk.ioctlup		= 0;
		smmsgblk.channel        = smdCardAndChannelId;

		rc = ioctl(handle,kSMDrvrCtlCmdBindToEvent,&smmsgblk);

		if (rc != 0)
		{
			result = ERR_SM_DEVERR;

			close(handle);
		}
		else
		{
			*eventId = handle;
		}
	}
	else
	{
		result = ERR_SM_NO_RESOURCES;
	}

	return result;
}


int smd_ev_create( tSMEventId* eventId, tSMChannelId channelId, int eventKind, int eventScope )
{
	int				rc;
	tSMChannelId 	result;
	SMMSGBLK		smmsgblk;
	int				dacpDev;
	tSMChannelId	smdCardAndChannelId;

	result = 0;

	if (eventScope == kSMChannelSpecificEvent)
	{
		/*
		 * Obtain DACP (not smd) card no. with which event should be associated
		 * and a smd type channelId, get these through ioctl on channel handle.
		 */
	   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdGetBindId;
	   	smmsgblk.length			= 0;
	   	smmsgblk.command		= eventKind;
	   	smmsgblk.module			= -1;
	   	smmsgblk.apiLibVersion 	= ((kSMDVersionMaj<<8) + kSMDVersionMin);
	   	smmsgblk.fwLibVersion  	= -1;	
	   	smmsgblk.error   		= 0;
		smmsgblk.ioctlup		= 0;
		smmsgblk.channel        = 0;

		rc = ioctl((int)channelId,kSMDrvrCtlCmdGetBindId,&smmsgblk);

		if (rc < 0)
		{
			result = ERR_SM_DEVERR;
		}
		else if (smmsgblk.error != 0)
		{
			result = smmsgblk.error;
		}
		else
		{
			smdCardAndChannelId = smmsgblk.channel;
 
			dacpDev = (((int)smdCardAndChannelId) >> 12) & 0x0f;
		}
	}
	else
	{
		/*
		 * Any channel event associated with DACP card zero.
		 */ 
		dacpDev 			= 0;
		smdCardAndChannelId = -1;
	}

	if (result == 0)
	{
		result = smd_ev_open_and_bind(eventId,dacpDev,eventKind,smdCardAndChannelId);
	}

	return result;
}


int smd_ev_create_allkinds_any( tSMEventId* eventId )
{
	tSMChannelId 	result;
	int				dacpDev;
	tSMChannelId	smdCardAndChannelId;

	/*
	 * Any channel event associated with DACP card zero.
	 */ 
	dacpDev 			= 0;
	smdCardAndChannelId = -1;

	result = smd_ev_open_and_bind(eventId,dacpDev,-1,smdCardAndChannelId);

	return result;
}


int smd_ev_create_allkinds_specific( tSMEventId* eventId, tSMChannelId channelId )
{
	int				rc;
	tSMChannelId 	result;
	SMMSGBLK		smmsgblk;
	int				dacpDev;
	tSMChannelId	smdCardAndChannelId;

	result = 0;

	/*
	 * Obtain DACP (not smd) card no. with which event should be associated
	 * and a smd type channelId, get these through ioctl on channel handle.
	 */
   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdGetBindId;
   	smmsgblk.length			= 0;
   	smmsgblk.command		= -1;
   	smmsgblk.module			= -1;
   	smmsgblk.apiLibVersion 	= ((kSMDVersionMaj<<8) + kSMDVersionMin);
   	smmsgblk.fwLibVersion  	= -1;	
   	smmsgblk.error   		= 0;
	smmsgblk.ioctlup		= 0;
	smmsgblk.channel        = 0;

	rc = ioctl((int)channelId,kSMDrvrCtlCmdGetBindId,&smmsgblk);

	if (rc < 0)
	{
		result = ERR_SM_DEVERR;
	}
	else if (smmsgblk.error != 0)
	{
		result = smmsgblk.error;
	}
	else
	{
		smdCardAndChannelId = smmsgblk.channel;

		dacpDev = (((int)smdCardAndChannelId) >> 12) & 0x0f;
	}

	if (result == 0)
	{
		result = smd_ev_open_and_bind(eventId,dacpDev,-1,smdCardAndChannelId);
	}

	return result;
}


/*
 * Returns < 0 if error, 0 if nothing was aborted else count of aborts.
 */
int smd_ev_abort( int evKind, int evScope, int channelIx )
{
	int				result;
	int				rc;
	tSMDevHandle 	smControlDevice;
	SMMSGBLK		smmsgblk;

	result = 0;

	smControlDevice = smd_open_ctl_dev( );

	if (smControlDevice != kSMNullDevHandle)
	{
		/*
		 * Abort any uncompleted event waits.
		 */
	   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdAbortEventWait;
	   	smmsgblk.length			= 0;
	   	smmsgblk.command		= evKind;
	   	smmsgblk.module			= -1;
	   	smmsgblk.apiLibVersion 	= ((kSMDVersionMaj<<8) + kSMDVersionMin);
	   	smmsgblk.fwLibVersion  	= -1;	
	   	smmsgblk.error   		= 0;
		smmsgblk.ioctlup		= 0;
		smmsgblk.channel        = (evScope == kSMChannelSpecificEvent) ? channelIx : -1;

		rc = ioctl((int)smdControlDevHandle,kSMDrvrCtlCmdAbortEventWait,&smmsgblk);

		if (rc < 0)
		{
			result = ERR_SM_DEVERR;
		}
		else if (smmsgblk.error != 0)
		{
			result = smmsgblk.error;
		}
	}
	else
	{
		result = ERR_SM_DEVERR;
	}

	return result;
}


int smd_ev_free( tSMEventId eventId )
{
	int result;
	int rc;

	result = 0;

	if (close((int) eventId) != 0)
	{
		result = ERR_SM_DEVERR;
	}

	return result;
}


int smd_ev_wait( tSMEventId eventId )
{
	int result;

	result = smd_ioctl_ev_wait(eventId);

	if (result > 0)
	{
		result = 0;
	}

	return result;
}


static int smd_ev_allkinds_wait( tSMEventId eventId, int* isWrite, int* isRead, int* isRecog )
{
	int result;

	*isWrite 	= 0;
	*isRead		= 0;
	*isRecog 	= 0;

	result = smd_ioctl_ev_wait(eventId);

	if (result > 0)
	{
		if (result & (1<<kSMEventTypeWriteData))
		{
			*isWrite = 1;
		}

		if (result & (1<<kSMEventTypeReadData))
		{
			*isRead = 1;
		}

		if (result & (1<<kSMEventTypeRecog))
		{
			*isRecog = 1;
		}

		result = 0;
	}

	return result;
}


int smd_ev_allkinds_any_wait( tSMEventId eventId, int* isWrite, int* isRead, int* isRecog )
{
	return smd_ev_allkinds_wait(eventId,isWrite,isRead,isRecog);
}


int smd_ev_allkinds_specific_wait( tSMEventId eventId, int* isWrite, int* isRead, int* isRecog )
{
	return smd_ev_allkinds_wait(eventId,isWrite,isRead,isRecog);
}


#endif


#ifdef SM_POLL_UNIX

#ifdef __linux__

/*
 * Linux 2.2 does not allow multiple threads to get deterministic results
 * invoking poll with disjoint event sets on the same fd simultaneously, so 
 * create new fd for each event, and mark in driver as special event fd.
 */
static int smd_ev_clone_channel( tSMChannelId channelId, int eventKind, int* fd )
{
	int				rc;
	int				channelIx;
	char			channelDeviceName[20];
	int				handle;
	SMMSGBLK		smmsgblk;

	rc = 0;

	channelIx = sm_get_channel_ix(channelId);

	if (channelIx < 0)
	{
		rc = ERR_SM_DEVERR;
	}
	else
	{
		strcpy(&channelDeviceName[0],"/dev/mvsm");

		sprintf(	&channelDeviceName[strlen(&channelDeviceName[0])],
					"%03d",
					(((int)(1+channelIx)))									);

		handle = open(&channelDeviceName[0],O_RDWR);

		if (handle < 0)
		{
			rc = ERR_SM_DEVERR;
		}
		else
		{
			*fd = handle;

		   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdBindToEvent;
		   	smmsgblk.length			= 0;
		   	smmsgblk.command		= eventKind;
		   	smmsgblk.module			= -1;
		   	smmsgblk.apiLibVersion 	= ((kSMDVersionMaj<<8) + kSMDVersionMin);
		   	smmsgblk.fwLibVersion  	= -1;	
		   	smmsgblk.error   		= 0;
			smmsgblk.ioctlup		= 0;
			smmsgblk.channel        = 1+channelIx;

			ioctl(handle,kSMDrvrCtlCmdBindToEvent,&smmsgblk);

			rc = 0;
		}
	}

	return rc;
}


static int smd_ev_clone_control( int eventKind, int* fd  )
{
	int				rc;
	int				handle;
	SMMSGBLK		smmsgblk;

	rc = 0;

	handle = open(smdevname,O_RDWR);

	if (handle < 0)
	{
		rc = ERR_SM_DEVERR;
	}
	else
	{
		*fd = handle;

	   	smmsgblk.ctlcmd			= kSMDrvrCtlCmdBindToEvent;
	   	smmsgblk.length			= 0;
	   	smmsgblk.command		= eventKind;
	   	smmsgblk.module			= -1;
	   	smmsgblk.apiLibVersion 	= ((kSMDVersionMaj<<8) + kSMDVersionMin);
	   	smmsgblk.fwLibVersion  	= -1;	
	   	smmsgblk.error   		= 0;
		smmsgblk.ioctlup		= 0;
		smmsgblk.channel        = 0;

		ioctl(handle,kSMDrvrCtlCmdBindToEvent,&smmsgblk);
	}

	return rc;
}

static void smd_ev_free_cloned_fd( int clonedFD )
{
	close(clonedFD);
}

#else

static int smd_ev_clone_channel( tSMChannelId channelId, int eventKind, int* fd )
{
	*fd = channelId;

	return 0;
}

static int smd_ev_clone_control( int eventKind, int* fd )
{
	*fd = smdControlDevHandle;

	return 0;
}

static void smd_ev_free_cloned_fd( int clonedFD )
{
}

#endif

int smd_ev_create( tSMEventId* eventId, tSMChannelId channelId, int eventKind, int eventScope )
{
	int	rc;

	rc = 0;

	smd_open_ctl_dev();

	if ((eventKind == kSMEventTypeWriteData) || (eventKind == kSMEventTypeReadData))
	{
		if (eventScope == kSMChannelSpecificEvent)
		{
			rc = smd_ev_clone_channel(channelId,eventKind,&(eventId->fd));
		}
		else
		{
			 rc = smd_ev_clone_control(eventKind,&(eventId->fd));
		}

#ifdef __linux__
		eventId->mode = (eventKind == kSMEventTypeWriteData) ? POLLOUT : POLLIN;
#else
		eventId->mode = (eventKind == kSMEventTypeWriteData) ? POLLWRNORM : POLLRDNORM;
#endif
	}
	else if (eventKind == kSMEventTypeRecog)
	{
		if (eventScope == kSMChannelSpecificEvent)
		{
			rc = smd_ev_clone_channel(channelId,eventKind,&(eventId->fd));
		}
		else
		{
			 rc = smd_ev_clone_control(eventKind,&(eventId->fd));
		}

#ifdef __linux__
		eventId->mode = POLLIN;     /* POLLRDBAND isn't use in kernel */
#else
		eventId->mode = POLLRDBAND;
#endif
	}
	else
	{
		rc = ERR_SM_NO_RESOURCES;
	}

	return rc;
}


int smd_ev_free( tSMEventId eventId )
{
	smd_ev_free_cloned_fd(eventId.fd);

	return 0;
}


int smd_ev_wait( tSMEventId eventId )
{
	int				result;
	int				rc;
	struct pollfd 	fds[1];

	result = 0;

	fds[0].fd      = eventId.fd;
	fds[0].events  = eventId.mode;
	fds[0].revents = 0;

	rc = poll(&fds[0],(unsigned long) 1,-1);

	if (rc < 0)
	{
		if (errno == EINTR)
		{
			result = ERR_SM_OS_INTERRUPTED_WAIT;
		}
		else if (rc != 0)
		{
			result = ERR_SM_DEVERR;
		}
	}

	return result;
}

#endif

