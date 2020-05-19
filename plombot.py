""" plombot """
import asyncio
import ctypes.util
import logging
from sys import argv

import random
import discord
from discord.ext import commands

import keys


# Settings
DEFAULT_VOLUME = 20
DEFAULT_PREFIX = ";"
CLIENT_ID = 412809807842639883
SUPPORT_SERVER = "https://discord.gg/Czj2g9c"
logging.getLogger('discord').disabled = True


def get_prefix(bot, message):
    if not message.guild:
        prefix = bot.default_prefix
    else:
        # Check cached prefixes
        try:
            prefix = bot.prefixes[message.guild.id]
        except KeyError:
            # Load from database
            bot.db.cursor.execute(f"SELECT prefix FROM guilds WHERE id = '{message.guild.id}'")
            result = bot.db.cursor.fetchone()
            if result:
                prefix = result[0]
            else:
                prefix = bot.default_prefix
            # save to cache
            bot.prefixes[message.guild.id] = prefix

    return prefix


class Plombot(commands.Bot):
    def __init__(self, prefix=";"):
        self.default_prefix = prefix
        super().__init__(command_prefix=get_prefix, case_insensitive=True)
        self.load_extension('cogs.admin')
        self.load_extension('cogs.database')
        self.load_extension('cogs.dota')
        self.load_extension('cogs.error_handler')
        self.load_extension('cogs.spotify')
        self.load_extension('cogs.youtube')
        self.load_extension('cogs.music') # must be loaded after spotify/youtube
        self.db = self.get_cog('Database')
        self.prefixes = {}

        if not discord.opus.is_loaded():
            lib = ctypes.util.find_library('opus')
            discord.opus.load_opus(lib)

        @self.event
        async def on_ready():
            """ Called after the bot successfully connects to Discord servers """
            print(f"Connected as {self.user.display_name}")

            # Change presence to "Playing music in 69 guilds | ;help"
            text = f"music in {len(self.guilds)} guilds | {DEFAULT_PREFIX}help"
            activity = discord.Activity(name=text, type=discord.ActivityType.streaming)
            await self.change_presence(activity=activity)

            # Print guild info
            print(f"Active in {len(self.guilds)} guilds:")
            user_count = 0
            for guild in self.guilds:
                count = len(guild.members) - 1 # remove self from list
                print(f" - [{guild.id}] ({count} users) {guild.name} (Owner: {guild.owner.name}#{guild.owner.discriminator} {guild.owner.id})")
                # add user count, exclude discord bot list
                if guild.id != 264445053596991498:
                    user_count += count
            print(f"Total user reach: {user_count}")

        @self.event
        async def on_voice_state_update(member, before, after):
            """ Called when a user changes their voice state

            Args:
                member – The Member whose voice states changed.
                before – The VoiceState prior to the changes.
                after  – The VoiceState after to the changes.

            Leaves and clears the queue if the bot is left alone for 3 minutes
            """
            if after is not None:
                pass

            if before is not None:
                # Find the voice client for this guild
                try:
                    voice = [vc for vc in self.voice_clients if vc.guild == member.guild][0]
                except IndexError:
                    # bot does not have active voice client in this guild
                    return

                # save the current channel
                channel = voice.channel

                # Loop for 120 seconds; if nobody comes back, clear the queue and d/c
                timeout = 180  # seconds before disconnecting
                step = 10 # seconds between checks
                for _ in range(0, int(timeout/step)):
                    # stop looping if a non bot comes back
                    if any([not user.bot for user in voice.channel.members]):
                        return
                    # stop looping if client is no longer connected, or if the bot moves
                    if not voice.is_connected():
                        return
                    if voice.channel is not channel: # bot moved
                        return
                    await asyncio.sleep(step)

                cog = self.get_cog('Music')
                player = await cog.get_player(member)
                await player.stop()

        @self.event
        async def on_guild_join(guild):
            channel = discord.utils.get(guild.text_channels, name="general")
            if len(guild.text_channels) > 0 and channel is None:
                channel = guild.text_channels[0]
            await self.send_help(channel=channel, prefix=DEFAULT_PREFIX)

    async def send_embed(self, channel, color=None, footer=None, footer_icon=None, subtitle=None,
        subtext=None, text=None, title=None, thumbnail=None):
        """ Sends a message to a channel, and returns the discord.Message of the sent message.

        If the text is over 2048 characters, subtitle and subtext fields are ignored and the
        message is split up into chunks. The first message will have the title and thumbnail,
        and only the last message will have the footer. Returns the last message sent.
        """
        MSG_LIMIT = 2048

        # Use a random color if none was given
        if color is None:
            color = random.randint(0, 0xFFFFFF)

        # Text fits into one message, add all fields passed to function
        if text is None or len(text) <= MSG_LIMIT:
            embed = discord.Embed(color=color)
            if footer is not None:
                if footer_icon is not None:
                    embed.set_footer(text=footer, icon_url=footer_icon)
                else:
                    embed.set_footer(text=footer)
            if subtitle is not None or subtext is not None:
                embed.add_field(name=subtitle, value=subtext, inline=True)
            if thumbnail is not None:
                embed.set_thumbnail(url=thumbnail)
            if title is not None:
                embed.title = title
            if text is not None:
                embed.description = text

            # Send the single message
            return await channel.send(embed=embed)

        # Text must be broken up into chunks
        i = 0 # message index
        lines = text.split("\n")
        while lines:
            # Construct the text of this message
            text = ""
            while True:
                if not lines:
                    break
                line = lines.pop(0) + '\n'

                # next line fits in this message, add it
                if len(text) + len(line) < MSG_LIMIT:
                    text += line

                # one line is longer than max length of message, split the line and put the rest back
                elif len(line) > MSG_LIMIT:
                    cutoff = MSG_LIMIT - len(text)
                    next_line = line[:cutoff]
                    remainder = line[cutoff:-1]
                    text += next_line
                    lines.insert(0, remainder)
                # message is full - send it
                else:
                    lines.insert(0, line)
                    break

            embed = discord.Embed(color=color)
            embed.description = text

            # First message in chain - add the title and thumbnail
            if i == 0:
                if title is not None:
                    embed.title = title
                if thumbnail is not None:
                    embed.set_thumbnail(url=thumbnail)
                if subtitle is not None or subtext is not None:
                    embed.add_field(name=subtitle, value=subtext, inline=True)

            # Last message in chain - add the footer
            if not lines:
                if footer is not None:
                    if footer_icon is not None:
                        embed.set_footer(text=footer, icon_url=footer_icon)
                    else:
                        embed.set_footer(text=footer)

            response = await channel.send(embed=embed)

            i = i + 1

        # Return the last message sent so reactions can be easily added
        return response

    async def delete_message(self, message):
        """ Deletes a message, ignoring NotFound errors """
        if message is not None:
            try:
                await message.delete()
            except discord.errors.NotFound:
                pass

    async def add_reactions(self, message, emojis):
        """ Adds emojis to a message, ignoring NotFound errors """
        if message is not None:
            try:
                for emoji in emojis:
                    await message.add_reaction(emoji)
            except discord.errors.NotFound:
                pass

    async def send_help(self, channel, prefix):
        """ Sends help message to the given channel """
        # Commands
        url = 'https://gitlab.com/avalonparton/plombot/wikis/Commands#commands'
        cmds = f"""**{prefix}play [link or query]** *Play music from YouTube and Spotify.*
                    **{prefix}playalbum [query]** *Play an album from Spotify.*
                    **{prefix}playartist [query]** *Play an artist's top tracks.*
                    **{prefix}volume** *Change the volume.*
                    **{prefix}video** *Enable video for a voice channel*
                    **{prefix}music** *Set the music channel*
                    **{prefix}dota** *See all the Dota commands.*
                    [**See all commands**]({url})"""

        # Invite and support links
        url_invite = f"https://discordapp.com/oauth2/authorize?client_id={CLIENT_ID}&scope=bot&permissions=1110453312"
        url_issue = "https://gitlab.com/avalonparton/plombot/issues"
        text = f"""[Invite **plombot**]({url_invite}) to another server.
                    [Report an issue]({url_issue}) on Gitlab.
                    [Join the support server]({SUPPORT_SERVER}) and ask for help."""

        embed = discord.Embed(color=0xFF69B4)
        embed.title = "Command List"
        embed.description = cmds
        embed.add_field(name="Support", value=text)
        embed.set_thumbnail(url="https://i.imgur.com/vY1nz0u.png") # logo with dropshadow
        await channel.send(embed=embed)


def main():
    # Run test bot if called with argument "dev"
    if len(argv) > 1 and argv[1] in 'dev':
        print("Starting plombot dev (prefix is !)")
        bot = Plombot("!")
        bot.run(keys.discord_token_dev)
    else:
        print("Starting plombot (prefix is ;)")
        bot = Plombot(";")
        bot.run(keys.discord_token)

if __name__ == '__main__':
    main()
