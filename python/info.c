#include <stdio.h>
#include <smdrvr.h>

int main(int argc, char *argv[])
{
	int rc;
	SM_CHANNEL_ALLOC_PLACED_PARMS alloc;
	SM_CHANNEL_INFO_PARMS info;

	memset(&alloc, 0, sizeof(alloc));

	rc = sm_channel_alloc_placed(&alloc);
	if (rc)
	{
		printf("sm_channel_alloc_placed failed: %d\n", rc);
		return rc;
	}

	memset(&info, 0, sizeof(info));

	info.channel = alloc.channel;
	rc = sm_channel_info(&info);
	if (rc)
	{
		printf("sm_channel_info failed: %d\n", rc);
		return rc;
	}

	printf("card: %d\n", info.card);
}
