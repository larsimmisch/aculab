/***********************************************************************\

  Module:		smttslib.h
  Description:	Constants, structures and API prototypes for smttslib.dll 
  Author:		A Lowry
  Copyright:	Aculab plc 1999
  
\***********************************************************************/

#ifndef __SMTTSLIB_H
#define __SMTTSLIB_H

//#include <windows.h>
#include "smhlib.h"

/* System specifications and default settings */
#define kSMTTSMaxServers       5
#define kSMTTSMaxLanguages     5
#define kSMTTSMaxVoices        20
#define kSMTTSMaxPreps         5
#define kSMTTSMaxEmails        1
#define kSMTTSMaxSynths        1
#define kSMTTSMaxEngines       5
#define kSMTTSMsgHeuristic     1
#define kSMTTSMsgNewline       2
#define kSMTTSDefaultVoiceID   0
#define kSMTTSDefaultPitch     4
#define kSMTTSDefaultSpeed     4
#define kSMTTSDefaultVolume    0
#define kSMTTSDefaultSilence   250
#define kSMTTSDefaultSession   -1
#define kSMTTSDefaultSampleType	kSMTTSSampleTypeAlaw
#define kSMTTSSampleTypeAlaw	1
#define kSMTTSSampleTypeMulaw	2
#define kSMTTSSampleTypeLinear	3
#define kSMTTSBindModeNone		0
#define kSMTTSBindModeProsody	1
#define kSMTTSBindModeSoundcard	2
#define kSMTTSBindModeFile		3
#define kSMTTSBindModeBuffer	4
#define kSMTTSExpandEmoticons	1
#define kSMTTSIgnoreEmoticons	2

/* Error codes for TTS */
#define ERR_BASE						-1000
#define ERR_SMTTS_NO_SUCH_SESSION		(ERR_BASE - 1)
#define ERR_SMTTS_NO_SUCH_CHANNEL		(ERR_BASE - 2)
#define ERR_SMTTS_NO_TTS_CHANNELS		(ERR_BASE - 3)
#define ERR_SMTTS_NO_RX_SOCKET			(ERR_BASE - 4)
#define ERR_SMTTS_NO_TX_SOCKET			(ERR_BASE - 5)
#define ERR_SMTTS_DEVERR				(ERR_BASE - 6)
#define ERR_SMTTS_UNINITIALIZED			(ERR_BASE - 7)
#define ERR_SMTTS_INITIALIZED			(ERR_BASE - 8)
#define ERR_SMTTS_CHANNEL_LOCKED		(ERR_BASE - 9)
#define ERR_SMTTS_NO_SUCH_VOICE			(ERR_BASE - 10)
#define ERR_SMTTS_VOICE_SETUP			(ERR_BASE - 11)
#define ERR_SMTTS_BAD_PARAMETER			(ERR_BASE - 12)
#define ERR_SMTTS_NO_WSA_STARTUP		(ERR_BASE - 13)
#define ERR_SMTTS_SPEAK_ERROR			(ERR_BASE - 14)
#define ERR_SMTTS_BAD_CONFIG_FILE		(ERR_BASE - 15)
#define ERR_SMTTS_TIMEOUT				(ERR_BASE - 16)
// new ones
#define ERR_SMTTS_NO_CONTROLLER			(ERR_BASE - 17)
#define ERR_SMTTS_CONTROLLER_ERROR		(ERR_BASE - 18)
#define ERR_SMTTS_SESSION_IN_USE		(ERR_BASE - 19)
#define ERR_SMTTS_CHANNEL_IN_USE		(ERR_BASE - 20)
#define ERR_SMTTS_COMPLETING			(ERR_BASE - 21)
#define ERR_SMTTS_COMPLETED				(ERR_BASE - 22)
#define ERR_SMTTS_SM_CHANNEL_LOCKED		(ERR_BASE - 23)
#define ERR_SMTTS_CLIENT_ERROR			(ERR_BASE - 24)
#define ERR_SMTTS_PROSODY_ERROR			(ERR_BASE - 25)
#define ERR_SMTTS_BAD_BIND_MODE			(ERR_BASE - 26)
#define ERR_SMTTS_ALREADY_BOUND			(ERR_BASE - 27)
#define ERR_SMTTS_NO_SUCH_SM_CHANNEL	(ERR_BASE - 28)
#define ERR_SMTTS_SOUNDCARD_LOCKED		(ERR_BASE - 29)
#define ERR_SMTTS_SOUNDCARD_ERROR		(ERR_BASE - 30)
#define ERR_SMTTS_AUDIO_FILE_ERROR		(ERR_BASE - 31)

#define MAX_LEN_STATUS 40

typedef int tSMTTSChannelId;

typedef struct smtts_voice {
	tSM_INT voiceID;
	char	name[20];
	char	gender;	/* not currently used */
	char	lang[20]; /* not currently used */
	tSM_INT samplerate; /* not currently used */
} SMTTS_VOICE;

typedef struct smtts_language { /* not currently used */
	tSM_INT		languageID;
	char		name[20];
	tSM_INT		nvoices;
	SMTTS_VOICE *voice;
} SMTTS_LANGUAGE;

typedef struct smtts_prep { /* not currently used */
	tSM_INT prepID;
	char	name[20];
	char	lang[20];
} SMTTS_PREP;

typedef struct smtts_synth { /* not currently used */
	tSM_INT synthID;
	char	name[20];
} SMTTS_SYNTH;

typedef struct smtts_engine { /* not currently used */
	tSM_INT engineID;
	char	name[20];
	char	lang[20];
} SMTTS_ENGINE;

typedef struct smtts_email { /* not currently used */
	tSM_INT emailID;
	char	name[20];
	char	lang[20];
} SMTTS_EMAIL;

typedef struct smtts_config_parms {
	tSM_INT		voiceID;
	tSM_INT		speed;
	tSM_INT		pitch;
	tSM_INT		volume;
	tSM_INT		trailing_silence;
	tSM_INT		msg_mode;
} SMTTS_CONFIG_PARMS;

typedef struct smtts_startup_parms {
	tSM_INT		firmwareID;
	tSM_INT		module;
} SMTTS_STARTUP_PARMS;

typedef struct smtts_session_alloc_parms {
	tSM_INT				sessionID;
	tSM_INT				user_config;
	SMTTS_CONFIG_PARMS	config_parms;
} SMTTS_SESSION_ALLOC_PARMS;

typedef struct smtts_channel_alloc_parms {
	tSMTTSChannelId	tts_chID;
} SMTTS_CHANNEL_ALLOC_PARMS;

typedef struct smtts_email_parms {
	tSM_INT	header_only;
	tSM_INT	emoticons;
	char *	date_prompt;
	char *	subject_prompt;
	char *	from_prompt;
	char *	after_indents_prompt;
	char *	forward_prompt;
	char *	reply_prompt;
	char *	reply_sep_prompt;
	char *	forward_sep_prompt;
	char *	file_attachment_prompt;
} SMTTS_EMAIL_PARMS;

typedef struct smtts_bind_parms {
	tSMTTSChannelId		tts_chID;
	tSM_INT             bind_mode;
	tSMChannelId		sm_chID;
	char				file[512];
	tSM_INT				sample_type;
} SMTTS_BIND_PARMS;

typedef struct smtts_speak_parms {
	tSMTTSChannelId		tts_chID;
	char *				text;
	tSM_INT				user_config;
	SMTTS_CONFIG_PARMS	config_parms;
	tSM_INT				aborted;
	tSM_INT				email;
	SMTTS_EMAIL_PARMS	email_parms;
} SMTTS_SPEAK_PARMS;

typedef struct smtts_read_samps_parms {
	tSMTTSChannelId		tts_chID;
	char *				samples;
	tSM_INT 			read_len;
} SMTTS_READ_SAMPS_PARMS;


typedef struct smtts_version {
	tSM_INT major;
	tSM_INT minor;
	tSM_INT step;
	tSM_INT custom;
	char status[MAX_LEN_STATUS];
} SMTTS_VERSION;

typedef struct smtts_sys_caps {
	SMTTS_VERSION	version;
	tSM_INT			nchannels;
	tSM_INT			nvoices;
	SMTTS_VOICE		voice[kSMTTSMaxVoices];
} SMTTS_SYS_CAPS;


/***********************************************************************\

	API Prototypes

\***********************************************************************/

#ifdef __cplusplus
extern "C" {
#endif

/* System management */

/* return codes
 0
 ERR_SMTTS_NO_WSA_STARTUP
 ERR_SMTTS_BAD_CONFIG_FILE
 ERR_SMTTS_NO_TX_SOCKET
 ERR_SMTTS_NO_RX_SOCKET
*/
int smtts_startup         (void);

/* return codes
 0
 ERR_SMTTS_UNINITIALIZED
*/
int smtts_shutdown        (void);

/* Session management */

/* return codes
 0
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_UNINITIALIZED
*/
int smtts_session_alloc   (SMTTS_SESSION_ALLOC_PARMS *alloc_parms);

/* return codes
 0
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
 ERR_SMTTS_SESSION_IN_USE
 */
int smtts_session_release (tSM_INT sessionID);

/* Channel management */

/* return codes
 0
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
 ERR_SMTTS_NO_TX_SOCKET
 ERR_SMTTS_NO_RX_SOCKET
 ERR_SMTTS_NO_TTS_CHANNELS
*/
int smtts_channel_alloc   (tSM_INT sessionID, SMTTS_CHANNEL_ALLOC_PARMS *alloc_parms);

/* return codes
 0
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
 ERR_SMTTS_CHANNEL_IN_USE
*/
int smtts_channel_release (tSM_INT sessionID, tSMTTSChannelId tts_chID);

/* Destination binding */

/* return codes
 0
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
 ERR_SMTTS_NO_SUCH_CHANNEL
 ERR_SMTTS_COMPLETING
 ERR_SMTTS_ALREADY_BOUND
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_SM_CHANNEL_LOCKED
 ERR_SMTTS_DEVERR
 ERR_SMTTS_NO_SUCH_SM_CHANNEL
 ERR_SMTTS_BAD_BIND_MODE
 ERR_SMTTS_NO_TX_SOCKET
*/
int smtts_bind_dest       (tSM_INT sessionID, SMTTS_BIND_PARMS *bind_parms);

/* Synthesis */

/* return codes
 0
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
 ERR_SMTTS_NO_SUCH_CHANNEL
 ERR_SMTTS_NO_TX_SOCKET
 ERR_SMTTS_NO_RX_SOCKET
 ERR_SMTTS_COMPLETING
 ERR_SMTTS_CLIENT_ERROR
*/
int smtts_speak_start     (tSM_INT sessionID, SMTTS_SPEAK_PARMS *speak_parms);

/* return codes
 0
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
 ERR_SMTTS_NO_SUCH_CHANNEL
 ERR_SMTTS_NO_TX_SOCKET
 ERR_SMTTS_CLIENT_ERROR
 ERR_SMTTS_PROSODY_ERROR
 ERR_SMTTS_AUDIO_FILE_ERROR
 ERR_SMTTS_SOUNDCARD_LOCKED
 ERR_SMTTS_SOUNDCARD_ERROR
*/
int smtts_speak_complete  (tSM_INT sessionID, SMTTS_SPEAK_PARMS *speak_parms);

/* return codes
 0
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
 ERR_SMTTS_NO_SUCH_CHANNEL
 ERR_SMTTS_NO_TX_SOCKET
*/
int smtts_speak_stop      (tSM_INT sessionID, SMTTS_SPEAK_PARMS *speak_parms);

/* return codes
 0
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
 ERR_SMTTS_NO_SUCH_CHANNEL
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_CLIENT_ERROR
 ERR_SMTTS_COMPLETED
*/
int smtts_speak_read_samps(tSM_INT sessionID, SMTTS_READ_SAMPS_PARMS *read_samps_parms);

/* System configuration */

/* return codes
 0
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
*/
int smtts_set_parameters  (tSM_INT sessionID, SMTTS_CONFIG_PARMS *config_parms);

/* return codes
 0
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
*/
int smtts_set_defaults    (tSM_INT sessionID);

/* System information */

/* return codes
 0
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_UNINITIALIZED
 ERR_SMTTS_NO_SUCH_SESSION
*/
int smtts_get_config      (tSM_INT sessionID, SMTTS_CONFIG_PARMS *config_parms);

/* return codes
 0
 ERR_SMTTS_BAD_PARAMETER
 ERR_SMTTS_NO_TX_SOCKET
 ERR_SMTTS_NO_RX_SOCKET
*/
int smtts_get_sys_caps    (SMTTS_SYS_CAPS *sys_caps);

#ifdef __cplusplus
}
#endif

#endif
