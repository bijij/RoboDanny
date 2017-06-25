from discord.ext import commands
import asyncio

class _ContextDBAcquire:
    __slots__ = ('ctx', 'timeout')

    def __init__(self, ctx, timeout):
        self.ctx = ctx
        self.timeout = timeout

    def __await__(self):
        return self.ctx._acquire(self.timeout).__await__()

    async def __aenter__(self):
        await self.ctx._acquire(self.timeout)
        return self.ctx.db

    async def __aexit__(self, *args):
        await self.ctx.release()

class Context(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pool = self.bot.pool
        self.db = None

    async def entry_to_code(self, entries):
        width = max(len(a) for a, b in entries)
        output = ['```']
        for name, entry in entries:
            output.append(f'{name:<{width}}: {entry}')
        output.append('```')
        await self.send('\n'.join(output))

    async def indented_entry_to_code(self, entries):
        width = max(len(a) for a, b in entries)
        output = ['```']
        for name, entry in entries:
            output.append(f'\u200b{name:>{width}}: {entry}')
        output.append('```')
        await self.send('\n'.join(output))

    def __repr__(self):
        # we need this for our cache key strategy
        return '<Context>'

    @property
    def session(self):
        return self.bot.session

    async def too_many_matches(self, matches, entry):
        await self.send('There are too many matches... Which one did you mean? **Only say the number**.')
        await self.send('\n'.join(map(entry, enumerate(matches, 1))))

        def check(m):
            return m.content.isdigit() and m.author.id == ctx.author.id and m.channel == ctx.channel.id

        # only give them 3 tries.
        for i in range(3):
            try:
                message = await self.wait_for('message', check=check, timeout=10.0)
            except asyncio.TimeoutError:
                raise ValueError('Took too long. Goodbye.')

            index = int(message.content)
            try:
                return matches[index - 1]
            except:
                await self.send(f'Please give me a valid number. {2 - i} tries remaining...')

        raise ValueError('Too many tries. Goodbye.')

    async def prompt(self, message, *, timeout=60.0, delete_after=True, reacquire=True):
        """An interactive reaction confirmation dialog.

        Parameters
        -----------
        message: str
            The message to show along with the prompt.
        timeout: float
            How long to wait before returning.
        delete_after: bool
            Whether to delete the confirmation message after we're done.
        reacquire: bool
            Whether to release the database connection and then acquire it
            again when we're done.

        Returns
        --------
        Optional[bool]
            ``True`` if explicit confirm,
            ``False`` if explicit deny,
            ``None`` if deny due to timeout
        """

        if not self.channel.permissions_for(self.me).add_reactions:
            raise RuntimeError('Bot does not have Add Reactions permission.')

        fmt = f'{message}\n\nReact with \N{WHITE HEAVY CHECK MARK} to confirm or \N{CROSS MARK} to deny.'

        author_id = self.author.id
        msg = await self.send(fmt)

        confirm = None

        def check(emoji, message_id, channel_id, user_id):
            nonlocal confirm

            if message_id != msg.id or user_id != author_id:
                return False

            codepoint = str(emoji)

            if codepoint == '\N{WHITE HEAVY CHECK MARK}':
                confirm = True
                return True
            elif codepoint == '\N{CROSS MARK}':
                confirm = False
                return True

            return False

        for emoji in ('\N{WHITE HEAVY CHECK MARK}', '\N{CROSS MARK}'):
            await msg.add_reaction(emoji)

        if reacquire:
            await self.release()

        try:
            await self.bot.wait_for('raw_reaction_add', check=check, timeout=timeout)
        except asyncio.TimeoutError:
            confirm = None

        if reacquire:
            await self.acquire()

        if delete_after:
            await msg.delete()

        return confirm

    def tick(self, opt, label=None):
        emoji = '<:check:316583761540022272>' if opt else '<:xmark:316583761699536896>'
        if label is not None:
            return f'{emoji}: {label}'
        return emoji

    async def _acquire(self, timeout):
        if self.db is None:
            self.db = await self.pool.acquire(timeout=timeout)
        return self.db

    def acquire(self, *, timeout=None):
        """Acquires a database connection from the pool. e.g. ::

            async with ctx.acquire():
                await ctx.db.execute(...)

        or: ::

            await ctx.acquire()
            try:
                await ctx.db.execute(...)
            finally:
                await ctx.release()
        """
        return _ContextDBAcquire(self, timeout)

    async def release(self):
        """Releases the database connection from the pool.

        Useful if needed for "long" interactive commands where
        we want to release the connection and re-acquire later.

        Otherwise, this is called automatically by the bot.
        """
        # from source digging asyncpg source, releasing an already
        # released connection does nothing

        if self.db is not None:
            await self.bot.pool.release(self.db)
            self.db = None

    async def show_help(self, command=None):
        """Shows the help command for the specified command if given.

        If no command is given, then it'll show help for the current
        command.
        """
        cmd = self.bot.get_command('help')
        command = command or self.command.qualified_name
        await self.invoke(cmd, cmd=command)
