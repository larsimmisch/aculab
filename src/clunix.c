/*------------------------------------------------------------*/
/* ACULAB plc                                                 */
/*------------------------------------------------------------*/
/*                                                            */
/*                                                            */
/* Program File Name : clunix.c                               */
/*                                                            */
/*           Purpose : Operating System Specifics for Call    */
/*                     control library                        */
/*                                                            */
/*       Create Date : 19th October 1992                      */
/*                                                            */
/*                                                            */
/*------------------------------------------------------------*/
/*                                                            */
/*                                                            */
/* Change History                                             */
/*                                                            */
/* rev:  v5.10.0       07/03/2003 for V5.10.0 Release         */
/*                                                            */
/*------------------------------------------------------------*/

/*
 * Include XPG 4.2 for cmsg.
 */
#ifdef __sun
#define _XPG4_2
#endif

#include "mvcldrvr.h"
#include "ras_info.h"
#include "pipe_interface.h"

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <pthread.h>
#include <semaphore.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/select.h>
#include <sys/uio.h>
#include <stropts.h>

#define FALSE  0
#define TRUE   1

#ifndef ACU_DIGITAL
typedef struct msgblk {
                      int  status;
                      union ioctlu * ioctlup;
                      } MSGBLK;
#endif

extern ACU_INT  card_2_voipcard ( ACU_INT  card );

/*----------------- local functions -----------------*/

int  clopen        ( char * );
char * cldev       ( void   );
int  clioctl       ( ACU_INT, IOCTLU *, ACU_INT, int, int );
int  clpblock_ioctl  ( ACU_INT, V5_PBLOCK_IOCTLU *, ACU_INT, int );
void clclose       ( void );
void clspecial     ( void );

int  clfileopen  ( char * );
int  clfileread  ( int, char *, unsigned int );
int  clfileclose ( int );
ACU_INT srvioctl(ACU_INT function, IOCTLU *pioctlu, int len,
		 int board_card_number, int voip_protocol_number);

int create_pipe_admin_thread(void);
const ACU_INT *get_voip_protocol_index_array(int *num_of_protocols);
int pipe_client_send_application_terminated(void);

/*----------------- local data ----------------------*/

#ifdef ACU_SOLARIS_SPARC
static char cldevname[] = "/dev/aculab/ACUc0";
#else
static char cldevname[] = { "/dev/mvcl0" };
#endif

static char clpipebasename[] = { "/var/run/aculab/" };

#define MAXNUMPIPES 2
#define MAXPIPENAME 20

#ifdef _REENTRANT
/* Data used to bootstrap an admin thread */
struct pipe_startup_data {
	int number;
	sem_t started;
};
#endif

/* Data stored permanantly about pipes */
struct pipe_data {
	int fd;
	pthread_mutex_t write_lock;
	char name[MAXPIPENAME];
	sem_t read_complete;
	ACU_SERVICE_MSG svc_msg;
};

#define H323_PIPE_INDEX 0
#define SIP_PIPE_INDEX  1

/* KEEP THIS ARRAY IN SYNC WITH ABOVE #defines */
static struct pipe_data pipes[] = {
	{ -1, PTHREAD_MUTEX_INITIALIZER, "AcuVoIP" },
	{ -1, PTHREAD_MUTEX_INITIALIZER, "AcuSIP" },
};

/* Return data for get_voip_protocol_index_array */
static int running_pipe_count = 0;
static int usable_voip_indexes[MAXNUMPIPES] = {
	-1,
	-1,
};

extern int    clopened;
extern int    ncards;
extern CARD   clcard[NCARDS];

/*------------ OS specifics -------------*/
/* Operating systems specific fucntions  */
/*---------------------------------------*/

/*----------------- clopen --------------*/
/* open the driver                       */
/*                                       */
int clopen(char *cldevnp)
{
	return open(cldevnp, O_RDONLY);
}
/*---------------------------------------*/

/*----------------- cldev ---------------*/
/* return a pointer to the device name   */
/*                                       */
char *cldev()
{
	return cldevname;
}
/*---------------------------------------*/

/*-------------- clclose ----------------*/
/* close the driver                      */
/*                                       */
void clclose()
{
	int  i;

	clopened = FALSE;

	for (i = 0; i < ncards; i++)
	{
		close(clcard[i].clh);
	}
}
/*---------------------------------------*/

/*---------------- clioctl --------------*/
/* Call UNIX driver IOCTL                */
/*                                       */
int clioctl(ACU_INT function, IOCTLU * pioctl, ACU_INT card, 
	    ACU_INT unet, int len)
{
	/* Check for VoIP card */
	if (card >= 0 && clcard[card].voipservice == ACU_VOIP_ACTIVE) {
		int voip_protocol;

		/* Which protocol? */
		switch (call_type(unet)) {
		case S_H323:
			voip_protocol = H323_PIPE_INDEX;
			break;
		case S_SIP:
			voip_protocol = SIP_PIPE_INDEX;
			break;
		default:
			/* We've got a logic error somewhere */
			return ERR_NET;
		}
		
		return srvioctl(function,
				pioctl,
				len,
				card_2_voipcard(card), voip_protocol);
	}
	else 
	{
		MSGBLK msgblk;	
		int clh = clcard[card].clh;
		
		len = len;
		
		init_api_reg ( &pioctl->api_reg, len );
		
		msgblk.status = 0;
		msgblk.ioctlup = pioctl;
		
		ioctl ( clh, function, &msgblk );
		
		return ( msgblk.status );
	}
}
/*---------------------------------------*/

/*----------clpblock_ioctl --------------*/
/*                                       */
/* For UNIX, the V4 style pblock is used */
/* so simply convert this call into a V4 */
/* style ioctl....                       */

int clpblock_ioctl(ACU_INT function, V5_PBLOCK_IOCTLU *v5_pblockp, 
                   ACU_INT card, int len)
{
#ifdef ACU_SOLARIS_SPARC
    len = len;

    if (function != (ACU_INT) CALL_V5PBLOCK)
       return (ACU_INT) ERR_COMMAND;

    return (clioctl (CALL_V5PBLOCK,(IOCTLU *) &v5_pblockp->pblock_xparms,card,-1,sizeof(V5_PBLOCK_XPARMS)));
#else
    IOCTLU v4_ioctl ;

    len = len;

    /* UNIX drivers still expect old (v4) style pblock commands... */
    /* so we just convert the v5_pblock into a v4_pblock */

    if (function != (ACU_INT) CALL_V5PBLOCK)
       return (ACU_INT) ERR_COMMAND;

    v4_ioctl.v4_pblock_xparms.len = v5_pblockp->pblock_xparms.len ;
    v4_ioctl.v4_pblock_xparms.net = v5_pblockp->pblock_xparms.net ;

    /* V4 pblock contains a ptr to data, v5 contains the embedded data */
    v4_ioctl.v4_pblock_xparms.datap = &v5_pblockp->pblock_xparms.datap[0] ;

    return (clioctl (CALL_V4PBLOCK,&v4_ioctl,card,-1,sizeof(V4_PBLOCK_XPARMS)));
#endif

}
/*---------------------------------------*/

/*--------------- clspecial -------------*/
/* open the driver                       */
/*                                       */
void clspecial()
{
}
/*---------------------------------------*/

/*--------------- clfileopen ------------*/
/* open a disk file                      */
/*                                       */
int clfileopen(char *fnamep)
{
	return open(fnamep, O_RDONLY);
}
/*---------------------------------------*/

/*--------------- clfileread ------------*/
/* read a disk file                      */
/*                                       */
int clfileread(int fh, char *buffp, unsigned len)
{
	return read(fh, buffp, len);
}
/*---------------------------------------*/

/*--------------- clfileclose -----------*/
/* open the driver                       */
/*                                       */
int clfileclose(int fh)
{
	return close(fh);
}
/*---------------------------------------*/

/*---------- read_safely ----------------*/
/* Wrap read() taking account of EINTR   */
/* and partial reads.                    */
static int read_safely(int fd, void *buf, size_t size)
{
	ssize_t ret;
	size_t bytes_read = 0;
	char *loc = buf;

	while (bytes_read < size) {
		ret = read(fd, loc, size);

		/* Errors are not always fatal... */
		if (ret < 0) {
			if (errno == EINTR) {
				/* Got a signal or something, try again */
				continue;
			}

			return ERR_CFAIL;
		}

		/* A read of zero bytes is EOF */
		if (ret == 0) {
			return ERR_CFAIL;
		}

		/* Did we read everything? */
		if (ret == size) {
			return 0;
		} else {
			/* Partial read, advance buffer and try again */
			size -= ret;
			loc += ret;
		}
	}

	/* Oops. */
	return ERR_CFAIL;
}

/*---------init_pipe_admin_thread -------*/
/* Configure the pipe admin thread       */
/*                                       */
static int init_pipe_admin_thread(int pipe_number)
{
	int ret;
	int pipesockets[2];
	int bootsocket;
	struct sockaddr_un addr;
	char cmsgbuf[1000]; /* No CMSG_SPACE on Solaris */
	struct cmsghdr *cmsg;
	struct msghdr msg;
	struct iovec iov;

#ifdef _REENTRANT
	ret = sem_init(&(pipes[pipe_number].read_complete), 0, 0);
	if (ret != 0) {
		goto fail;
	}
#endif


	pipes[pipe_number].fd = -1;

	/* We need a socket to pass over to the pipe */
	ret = socketpair(PF_UNIX, SOCK_STREAM, 0, pipesockets);
	if (ret != 0) {
		goto fail_sem;
	}

	/* Now let's talk to the server */
	ret = socket(PF_UNIX, SOCK_DGRAM, 0);
	if (ret == 0) {
		goto fail_pipe;
	}
	bootsocket = ret;

	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	snprintf(&(addr.sun_path[0]), sizeof(addr.sun_path),
		 "%s%s", clpipebasename, pipes[pipe_number].name);

	ret = connect(bootsocket, (struct sockaddr *)&addr, 
		      sizeof(addr.sun_family) + strlen(addr.sun_path));
	if (ret != 0) {
		goto fail_bootsock;
	}

	/* Pass the pipe down to the daemon */
	memset(&msg, 0, sizeof(msg));
	memset(&cmsgbuf, 0, sizeof(cmsgbuf));

	msg.msg_control = cmsgbuf;
	msg.msg_controllen = sizeof(struct cmsghdr) + sizeof(int);
	
	cmsg = CMSG_FIRSTHDR(&msg);

	if (cmsg == NULL) {
		goto fail_bootsock;
	}

	cmsg->cmsg_level = SOL_SOCKET;
	cmsg->cmsg_type = SCM_RIGHTS;
	cmsg->cmsg_len = msg.msg_controllen;
	memcpy(CMSG_DATA(cmsg), &(pipesockets[1]), sizeof(int));

	/* 
	 * All we want to pass is the file descriptor but under
	 * Solaris sendmsg() fails unless you pass some data down with
	 * the descriptor so we also write a single byte of regular
	 * data.
	 */
	iov.iov_base = cmsgbuf;
	iov.iov_len = 1;
	msg.msg_iov = &iov;
	msg.msg_iovlen = 1;
	
	ret = sendmsg(bootsocket, &msg, 0);
	if (ret == -1) {
		goto fail_bootsock;
	}

	/* We don't need our copy of that descriptor any more */
	close(pipesockets[1]);
	close(bootsocket);

	pipes[pipe_number].fd = pipesockets[0];

	/* We're all set up and ready to go */
	return 0;

 fail_bootsock:
	close(bootsocket);

 fail_pipe:
	close(pipesockets[0]);
	close(pipesockets[1]);

 fail_sem:
#ifdef _REENTRANT
	sem_destroy(&(pipes[pipe_number].read_complete));
#endif

 fail:

	return ERR_CFAIL;
}
/*---------------------------------------*/

/*------------- pipe_admin_thread -------*/
/* thread responsible for managing the   */
/* communication with the services.      */
/*                                       */
#ifdef _REENTRANT
static void *pipe_admin_thread(void *t)
{
	struct pipe_startup_data *startup_data = t;
	int pipe_number = startup_data->number;
	
	sem_post(&(startup_data->started));

	while (1) {
		int ret;

		/* Look for a message header */
		ret = read_safely(pipes[pipe_number].fd, 
				  &(pipes[pipe_number].svc_msg), 
				  sizeof(pipes[pipe_number].svc_msg));
		if (ret != 0) {
			/* We're in big heap trouble here - abort */
			close(pipes[pipe_number].fd);
			pipes[pipe_number].fd = -1;
			pthread_exit(0);
		}

		/* Signal the blocked thread */
		ret = close(pipes[pipe_number].svc_msg.pendingMsgEvent);
		if (ret != 0) {
			/* Nobody home - don't get stuck */
			continue;
		}

		/* Wait till it's done with the pipe */
		ret = sem_wait(&(pipes[pipe_number].read_complete));
		if (ret != 0) {
			/* Oh dear */
			continue;
		}
	}

	return NULL;
}
#endif
/*---------------------------------------*/



/*--------------- srvioctl --------------*/
/* Fake ioctl() into service             */
/*                                       */
ACU_INT srvioctl(ACU_INT function, IOCTLU *pioctlu, int len,
			int board_card_number, int voip_protocol)
{
	ACU_SERVICE_MSG msg;
	int ret;
	struct iovec iov[4];
	int iov_count = 0;
	int iov_size = 0;
#ifdef _REENTRANT
	int block_pipe[2];
	int tmp;
#endif

	/* Sanity check */
	if (voip_protocol < 0 || voip_protocol > MAXNUMPIPES) {
		return ERR_NET;
	}

	/* Need a pipe to do stuff */
	if (pipes[voip_protocol].fd < 0) {
		return ERR_CFAIL;
	}

	/* Compose the message */
	init_api_reg (&pioctlu->api_reg, len);

	memset(&msg, 0, sizeof(msg));

	msg.voip_card = board_card_number;
	msg.function  = function;

	switch (function) {
	case CALL_GET_RAS_MSG:
	case CALL_SEND_RAS_MSG:
		msg.message_type = ADMIN_CHAN_RAS_MSG;
		break;

	default:
		msg.message_type = TLS_MSG_GENERIC_TLS;
	}

	/* We're going to assemble our data into an I/O vector */
	iov[iov_count].iov_base = &msg;
	iov[iov_count].iov_len = sizeof(msg);
	iov_size += sizeof(msg);
	iov_count++;

	switch (msg.message_type) {
	case TLS_MSG_GENERIC_TLS:
		/* Just write the ioctlu down */
		iov[iov_count].iov_base = pioctlu;
		iov[iov_count].iov_len = len;
		iov_size += len;
		iov_count++;
		break;

	case ADMIN_CHAN_RAS_MSG:
	{
		voip_admin_msg *admin_msg 
			= pioctlu->voip_admin_out_xparms.admin_msg;

		/* Special message type */
		if (function == CALL_GET_RAS_MSG) {
			break;
		}

		/* First the admin message... */
		iov[iov_count].iov_base = admin_msg;
		iov[iov_count].iov_len = sizeof(voip_admin_msg);
		iov_size += iov[iov_count].iov_len;
		iov_count++;

		/* ...then any aliases... */
		if (admin_msg->endpoint_alias_count > 0) {
			iov[iov_count].iov_base = admin_msg->endpoint_alias;
			iov[iov_count].iov_len
				= sizeof(alias_address) * admin_msg->endpoint_alias_count;
			iov_size += iov[iov_count].iov_len;
			iov_count++;
		}

		/* ...followed by any prefixes */
		if (admin_msg->prefix_count > 0) {
			iov[iov_count].iov_base = admin_msg->prefixes;
			iov[iov_count].iov_len
				= sizeof(alias_address) * admin_msg->prefix_count;
			iov_size += iov[iov_count].iov_len;
			iov_count++;
		}
	}
	break;

	default:
		break;
	}

#ifdef _REENTRANT
	/* We're almost ready to send. Make a pipe to block on if we
	 * need it.
	 */
	if (function != CALL_SEND_RAS_MSG) {
		ret = pipe(block_pipe);
		if (ret != 0) {
			return ERR_CFAIL;
		}

		/* Give one fd to the service - we'll block on the
		 * other closing. */
		msg.pendingMsgEvent = block_pipe[1];
	}

	/* Acquire the lock on the pipe */
	ret = pthread_mutex_lock(&(pipes[voip_protocol].write_lock));
	if (ret != 0) {
		close(block_pipe[0]);
		close(block_pipe[1]);
		return ERR_CFAIL;
	}
#endif

	/* Do the write */
	ret = writev(pipes[voip_protocol].fd, iov, iov_count);
	if (ret != iov_size) {
#ifdef _REENTRANT
		pthread_mutex_unlock(&(pipes[voip_protocol].write_lock));
		if (function != CALL_SEND_RAS_MSG) {
			close(block_pipe[0]);
			close(block_pipe[1]);
		}
#endif
		return ERR_CFAIL;
	}

#ifdef _REENTRANT
	/* We're done... */
	pthread_mutex_unlock(&(pipes[voip_protocol].write_lock));
#endif

	if (function == CALL_SEND_RAS_MSG) {
		return 0;
	}

	/* Wait for the service to get back to us */
#ifdef _REENTRANT
	ret = read(block_pipe[0], &tmp, sizeof(tmp));
	close(block_pipe[0]);
	if (ret != 0) {
		close(block_pipe[1]);
		return ERR_CFAIL;
	}

	/* Copy the message for naming simplicity */
	memcpy(&msg, &(pipes[voip_protocol].svc_msg), sizeof(msg));
#else
	ret = read_safely(pipes[voip_protocol].fd, &msg, sizeof(msg));
	if (ret != 0) {
		return ERR_CFAIL;
	}
#endif

	switch (msg.message_type) {
	case TLS_MSG_GENERIC_TLS:
		ret = read_safely(pipes[voip_protocol].fd, pioctlu, len);
		if (ret != 0) {
			goto fail;
		}
		break;

	case ADMIN_CHAN_RAS_MSG:
	{
		voip_admin_msg *admin_msg 
			= pioctlu->voip_admin_in_xparms.admin_msg;

		/* Help avoid errors... */
		admin_msg->prefixes = 0;
		admin_msg->endpoint_alias = 0;

		/* In error cases only the header is written back over
		 * the pipe.
		 */
		if (!msg.valid) {
			break;
		} 

		/* First get the message itself */
		ret = read_safely(pipes[voip_protocol].fd, admin_msg, 
				  sizeof(voip_admin_msg));

		if (ret != 0) {
			goto fail;
		}

		pioctlu->voip_admin_in_xparms.valid = 1;

		/* Any aliases to read? */
		if (admin_msg->endpoint_alias_count > 0) {
			admin_msg->endpoint_alias 
				= malloc(admin_msg->endpoint_alias_count
					 * sizeof(alias_address));
			if (admin_msg->endpoint_alias == 0) {
				goto fail;
			}
			
			ret = read_safely(pipes[voip_protocol].fd,
					  admin_msg->endpoint_alias,
					  admin_msg->endpoint_alias_count
					  * sizeof(alias_address));
			if (ret != 0) {
				free(admin_msg->endpoint_alias);
				goto fail;
			}
		}

		/* Prefixes? */
		if (admin_msg->prefix_count > 0) {
			admin_msg->prefixes 
				= malloc(admin_msg->prefix_count
					 * sizeof(alias_address));
			if (admin_msg->prefixes == 0) {
				free(admin_msg->endpoint_alias);
				goto fail;
			}
			
			ret = read_safely(pipes[voip_protocol].fd,
					  admin_msg->prefixes,
					  admin_msg->prefix_count
					  * sizeof(alias_address));
			if (ret != 0) {
				free(admin_msg->endpoint_alias);
				free(admin_msg->prefixes);
				goto fail;
			}
		}
		    
		break;
	}

	default:
		break;
	}

#ifdef _REENTRANT
	sem_post(&(pipes[voip_protocol].read_complete));
#endif
	return msg.command_error;

fail:
#ifdef _REENTRANT
	sem_post(&(pipes[voip_protocol].read_complete));
#endif
	return ERR_CFAIL;
}
/*---------------------------------------*/

/*---------- create_pipe_admin_thread ---*/
/* Create thread to read from pipe.      */
/*                                       */
int create_pipe_admin_thread(void)
{
	int i;
	int ret;
#ifdef _REENTRANT
	pthread_t t;
	struct pipe_startup_data startup;
       
	ret = sem_init(&(startup.started), 0, 0);
	if (ret != 0) {
		return ERR_CFAIL;
	}
#endif
	
	for (i = 0; i < MAXNUMPIPES; i++)
	{
		/* Try to connect to the daemon */
		ret = init_pipe_admin_thread(i);
		if (ret != 0) {
			/* If that didn't work loop and try the next daemon */
			continue;
		}

#ifdef _REENTRANT
		startup.number = i;

		ret = pthread_create(&t, NULL, &pipe_admin_thread, &startup);
		if (ret != 0) {
			sem_destroy(&(startup.started));
			return ERR_CFAIL;
		}

		/* We need to wait for the thread to start since we
		   pass it data from out stack */
		ret = sem_wait(&(startup.started)); 
		if (ret != 0) { 
			sem_destroy(&(startup.started)); 
			return ERR_CFAIL; 
		} 
#endif 
	}

#ifdef _REENTRANT
	sem_destroy(&(startup.started));
#endif

	return 0;
}

/*--- init_voip_index_array -------------*/
/* Initialise data for protcol indexes   */
static void init_voip_index_array(void)
{
	int i;

	for (i = 0; i < MAXNUMPIPES; i++) {
		if (pipes[i].fd != -1) {
			usable_voip_indexes[running_pipe_count++] = i;
		}
	}
}

/*--- get_voip_protocol_index_array -----*/
/* Get a pointer to the index of active  */
/* VoIP protocols                        */
const ACU_INT *get_voip_protocol_index_array(int *num_of_protocols)
{
#ifdef _REENTRANT
	static pthread_once_t init_array = { PTHREAD_ONCE_INIT };
	pthread_once(&init_array, init_voip_index_array);
#else
	static int init_done = 0;
	if (init_done == 0) {
		init_voip_index_array();
		init_done = 1;
	}
#endif

	if (!num_of_protocols) {
		return 0;
	}

	*num_of_protocols = running_pipe_count;

	return &(usable_voip_indexes[0]);
}

/*---------------------------------------*/

/* FIXME: kill */
int pipe_client_send_application_terminated(void)
{
	return ERR_COMMAND;
}

/*------------- end of file -------------*/
