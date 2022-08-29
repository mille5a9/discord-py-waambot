from umongo import Document
from umongo.fields import *

from internal.database_init import instance

@instance.register
class ActivePolls(Document):
    """Document to store the message ID and potential role filter. Used in add reaction listener to stop non-role-havers from responding to polls they shouldn't."""

    message_id = IntegerField(required=True)
    role_id = IntegerField(required=False)