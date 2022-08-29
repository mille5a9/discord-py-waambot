import nextcord as discord
from nextcord.ext import commands
from internal import constants
from database.ActivePolls import ActivePolls
from inspect import currentframe, getframeinfo
import re

class Poll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def find_poll(self, msgId):
        return await ActivePolls.find_one({'message_id': msgId})

    @commands.group(name='poll', invoke_without_command=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def poll(self, ctx, question: str, *options):
        """
        Create a poll with a question, up to ten answers, and an optional role filter.
        """
        # validate number of options
        if (len(options) < 1):
            print('No options to respond to poll: aborting...')
            await ctx.send(':rotating_light: You must include at least two options for people to respond with.')
            return
        if (len(options) > 11):
            print('Too many options for poll, not enough emojis: aborting...')
            await ctx.send(':rotating_list: You must include ten or less options, or else we run out of number emojis \:)')
            return
        
        allowed_role = ctx.message.role_mentions[0] if len(ctx.message.role_mentions) > 0 else None
        allowed_role_id = allowed_role.id if allowed_role is not None else 0
        if allowed_role_id != 0: options = options[:-1]

        neededReactions = []
        title = question
        output = '' if allowed_role_id == 0 else ('Only ' + allowed_role.mention + ' may respond to this poll.\n')

        for index, option in enumerate(options, start=1):
            neededReactions.append(constants.POLL_OPTION_EMOJI[index])
            output += '' + constants.POLL_OPTION_EMOJI[index] + ': ' + option + '\n'

        embed = discord.Embed()
        embed.add_field(name=title, value=output)
        msg = await ctx.send(embed=embed)

        for emoji in neededReactions:
            await msg.add_reaction(emoji)
        
        poll = ActivePolls(message_id=msg.id)
        poll['role_id'] = allowed_role_id
        await poll.commit()

    
    @poll.command(name='clear')
    @commands.is_owner()
    async def clear_polls(self, ctx):
        """
        Owner only. Clears the database of active poll message ID values.
        """
        polls = ActivePolls.find()
        # 'WrappedCursor' object is not iterable
        async def each(result, error):
            if error: raise error
            elif result:
                print('deleting poll from active log...')
                await result.delete()

        polls.each(callback=each)


    @commands.Cog.listener("on_reaction_add")
    @commands.bot_has_permissions(manage_messages=True)
    async def poll_reaction(self, reaction, user):
        print('Listener heard reaction add...')

        # validate reacted message is an active poll and reactor is not a bot
        if user.bot: return
        validPoll = await self.find_poll(reaction.message.id)
        if validPoll is None: return
        print('Poll is valid')

        # validate user is in the poll's role filter
        if validPoll['role_id'] != 0 and isinstance(user, discord.Member):
            print('Has role_id, and user is a Member')
            # check for poll's role id in member's role list, remove reaction if there is a match
            if len(list(role for role in user.roles if role.id == validPoll['role_id'])) == 0:
                print('Member does not have the role for the poll')
                await reaction.message.remove_reaction(reaction.emoji, user)
        if len(await reaction.users().flatten()) == 1:
            print('Member reacted with an invalid option')
            await reaction.message.remove_reaction(reaction.emoji, user)

def setup(bot):
    bot.add_cog(Poll(bot))
