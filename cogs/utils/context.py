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
