/*------------------------------------------------------------*/
/* ACULAB Ltd                                                 */
/*------------------------------------------------------------*/
/*                                                            */
/*                                                            */
/* Program File Name : swunix.c                               */
/*                                                            */
/*           Purpose : Switch control library programs for    */
/*                     Multiple drivers                       */
/*                                                            */
/*            Author : Alan Rust                              */
/*                                                            */
/*       Create Date : 19th October 1992                      */
/*                                                            */
/*             Tools : CC compiler                            */
/*                                                            */
/*                                                            */
/*                                                            */
/*                                                            */
/*------------------------------------------------------------*/
/*                                                            */
/*                                                            */
/* Change History                                             */
/*                                                            */
/* cur:  3.03   swunix.c   Switch library for unix            */
/*                                                            */
/* rev:  1.00   10/10/92   agr   File created                 */
/* rev:  1.01   10/02/93   agr   Removed Statics              */
/* rev:  1.02   16/03/93   agr   tristate_switch added        */
/* rev:  1.03   06/04/93   agr   multiple driver support added*/
/* rev:  1.04   05/01/93   agr   set_idle function modified   */
/* rev:  2.10   14/02/96   pgd   First SCbus switch release   */
/* rev:  2.20   18/06/96   pgd   BR net streams>=32 release   */
/* rev:  2.30   17/10/96   pgd   Migrate to V4 generic etc.   */
/* rev:  3.01   31/03/98   pgd   V3 version.                  */
/* rev:  3.03   16/06/98   pgd   Eliminate __NEWC__           */
/*                                                            */
/*                                                            */
/*------------------------------------------------------------*/

#include "mvswdrvr.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <errno.h>

#ifdef SW_POLL_UNIX
 #include <poll.h>
 #define SW_EVENT_SERVICE
#endif
#ifdef SW_CLONE_UNIX
 #define SW_EVENT_SERVICE
#endif

#define NSWITCH 10  /* maximum number of switches supported */

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

#ifndef ACU_DIGITAL
int  ioctl ( 
#ifdef __STDC__
	int, int, SWMSGBLK * 
#endif
);
#endif

int nswitch = 0;

static int swopened = 0;

int swcard[NSWITCH];

#ifdef ACU_SOLARIS_SPARC
static char swdevname[] = "/dev/aculab/ACUs0";
#else
static char swdevname[] = "/dev/mvsw0";
#endif


/*
 * Open the driver.
 */
static int  swopen
#ifdef __STDC__
( char* swdevnp )
#else
( swdevnp ) char* swdevnp;
#endif
{
	return(open(swdevnp,O_RDONLY));
}


/*
 * Perform i/o call to the driver.
 */
int swioctl 
#ifdef __STDC__
( unsigned function, SWIOCTLU* pioctl, int swh, int size )
#else
( function, pioctl, swh, size ) unsigned function; SWIOCTLU* pioctl; int swh; int size;
#endif
{
	SWMSGBLK swmsgblk;

	swmsgblk.status    = 0;
	swmsgblk.swioctlup = pioctl;

	ioctl(swh,(int)function,&swmsgblk);

	return(swmsgblk.status);
}


/*
 * Close the driver.
 */
void swclose
#ifdef __STDC__
( void )
#else
( )
#endif
{
	int  i;

	swopened = 0;

	for ( i = 0; i < nswitch; i++ )
    {
		close(swcard[i]);
	}
}


/*-------------- swopendev --------------*/
/* open the driver                       */
/*                                       */
int swopendev
#ifdef __STDC__
(void)
#else
()
#endif
{
	int result;
	int addrnum;

	if ( swopened == 0 )
	{
		for ( nswitch = 0; nswitch < NSWITCH; nswitch++ )
        {
			addrnum = strlen ( swdevname ) - 1;

			swdevname[addrnum] = (char) (nswitch + '0');  /* set device name */
       
			swcard[nswitch] = swopen ( swdevname );

			if ( swcard[nswitch] < 0 )             /* check for error */
            {
            	break;                              /* device not there */
            }
		}

		if ( nswitch != 0 )
		{
			swopened = 1;
			result = 0;          /* some cards have opened */
		}
		else
		{
			result = MVIP_DEVICE_ERROR;
		}
	}
    else
	{
		result = 0;             /* already open */
	}

	return ( result );
}

/*
 * These calls only relevant to MC3 card switch driver.
 */
#ifndef SW_EVENT_SERVICE

int sw_ev_create( int swdrvr, tSWEventId* eventId )
{
	return ERR_SW_NO_RESOURCES;
}

int sw_ev_free( int swdrvr, tSWEventId eventId )
{
	return 0;
}

int sw_ev_wait( int swdrvr, tSWEventId eventId )
{
	return 0;
}

#else

#ifdef SW_CLONE_UNIX

static int sw_ev_abort_handle( int swh )
{
	int         result;
	int         rc;
	SWMSGBLK    swmsgblk;

	result = 0;

	swmsgblk.status    = kSWDrvrCtlCmdAbortEventWait;
	swmsgblk.swioctlup = 0;

	rc = ioctl(swh,(int)kSWDrvrCtlCmdAbortEventWait,&swmsgblk);

	if (rc < 0)
	{
		result = ERR_SW_DEVICE_ERROR;
	}
	else if (swmsgblk.status != 0)
	{
		result = swmsgblk.status;
	}

	return result;
}

int sw_ev_abort( int swdrvr, tSWEventId eventId )
{
	int result;

	result = swopendev();

	if (result == 0)
	{
		if (swdrvr < nswitch)
		{
			result = sw_ev_abort_handle(swcard[swdrvr]);
		}
		else
		{
			result = ERR_SW_INVALID_SWITCH;
		}
	}

	return result;
}

int sw_ev_create( int swdrvr, tSWEventId* eventId )
{
	int				result;
	int				rc;
	tSWEventId		eventBlockPtr;

	result = swopendev();

	if (result == 0)
	{
		if (swdrvr >= nswitch)
		{
			result = ERR_SW_INVALID_SWITCH;
		}
		else
		{
			*eventId = swcard[swdrvr];
		}
	}

	return result;
}


int sw_ev_free( int swdrvr, tSWEventId eventId )
{
	int result;

	result = swopendev();

	if (result == 0)
	{
		if (swdrvr >= nswitch)
		{
			result = ERR_SW_INVALID_SWITCH;
		}
		else
		{
			sw_ev_abort_handle(eventId);
		}
	}

	return result;
}


int sw_ev_wait( int swdrvr, tSWEventId eventId )
{
	SWMSGBLK  swmsgblk;
	int       result;
	int       rc;

	result = swopendev();

	if ((result == 0) && (eventId != 0))
	{
		swmsgblk.status    = kSWDrvrCtlCmdIOCTLEventWait;
		swmsgblk.swioctlup = 0;

		rc = ioctl((int)eventId,(int)kSWDrvrCtlCmdIOCTLEventWait,&swmsgblk);

		if (rc < 0)
		{
			if (errno == EINTR)
			{
				result = ERR_SW_OS_INTERRUPTED;
			}
			else
			{
				result = ERR_SW_DEVICE_ERROR;
			}
		}
		else if (swmsgblk.status >= 0)
		{
			result = 0;
		}
		else
		{
			result = swmsgblk.status;
		}
	}

	return result;
}

#else  /* SW_POLL_UNIX */

static int sw_ev_abort_handle( int swh )
{
	int result;

	result = close(swh);

	if (result == -1)
	{
		result = ERR_SW_DEVICE_ERROR;
	}

	return result;
}


int sw_ev_create( int swdrvr, tSWEventId* eventId )
{
	int result;

	result = swopendev();

	if (result == 0)
	{
		if (swdrvr >= nswitch)
		{
			result = ERR_SW_INVALID_SWITCH;
		}
		else
		{
			eventId->fd = swcard[swdrvr];
		}
	}

	return result;
}


int sw_ev_free( int swdrvr, tSWEventId eventId )
{
	int result;

	result = swopendev();

	if (result == 0)
	{
		if (swdrvr >= nswitch)
		{
			result = ERR_SW_INVALID_SWITCH;
		}
		else
		{
			sw_ev_abort_handle(eventId.fd);
		}
	}

	return result;
}


int sw_ev_wait( int swdrvr, tSWEventId eventId)
{
	int            result;
	int            rc;
	struct pollfd  fds[1];

	result = 0;

	result = swopendev();

	if (result == 0)
	{

		fds[0].fd      = eventId.fd;
		fds[0].events  = POLLIN;
		fds[0].revents = 0;

		rc = poll(&fds[0],(unsigned long) 1,-1);

		if (rc < 0)
		{
			if (errno == EINTR)
			{
				result = ERR_SW_OS_INTERRUPTED;
			}
			else if (rc != 0)
			{
				result = ERR_SW_DEVICE_ERROR;
			}
		}
	}

	return result;
}

#endif

#endif

