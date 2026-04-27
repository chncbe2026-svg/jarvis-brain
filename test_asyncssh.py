import asyncio
import asyncssh

async def test_ssh():
    # Attempt to connect to 192.168.10.152
    print("Connecting...")
    try:
        async with asyncssh.connect("192.168.10.152", port=22, username="root", password="Dinu@123#", known_hosts=None) as conn:
            print("Connected! Creating process...")
            process = await conn.create_process("ls -la", term_type='xterm', term_size=(120, 30))
            stdout, stderr = await process.communicate()
            print("STDOUT:")
            print(stdout)
    except Exception as e:
        print(f"Failed: {e}")

asyncio.run(test_ssh())
