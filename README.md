# Journal Library

**Try it: [journal-library.pages.dev](https://journal-library.pages.dev)** (a made-up sample journal; press ▶ Demo for the tour)

Your handwritten journal as a 3D bookshelf. Film yourself flipping through a notebook, and every page becomes a dated entry. Each year is a book on the shelf. Open one and you get months, then days, then the page itself next to what it says, plus everything you wrote on that same day in past years.

- **Film a notebook, get pages.** It picks the sharp frames from a phone video, splits each spread into pages, reads your handwriting and finds the date on each page. You check the dates on a review board (D, F, G on the keyboard).
- **A shelf of years.** 3D books for each year, category books (Career, Family, anything you make), and a Starred book. Turn pages with the arrow keys.
- **On this day.** Every day shows what you wrote on it 1 to 5 years ago, inside the same book.
- **Morning email.** Optional: those pages from past years, sent to you each morning.
- **Phone notes too.** Optional: daily notes from Obsidian (for example from an iPhone Shortcut) show up as entries with their photos.
- **Yours only.** Everything stays on your Mac. If you put it online, the site is only a doorway to your Mac, behind your password.
- **A lamp with a pull cord.** Pull it and the room warms up. Press `L` to do the same.

## What you need

- A Mac (it reads handwriting with macOS's built-in text recognition)
- [Homebrew](https://brew.sh), then: `brew install ffmpeg`
- Xcode command line tools: `xcode-select --install`

## Set it up

```bash
git clone https://github.com/kairothq/journal-library.git
cd journal-library
./setup.sh
```

That installs two Python packages, builds the text reader, starts the app and opens **http://localhost:8765/add**. The app starts again by itself whenever you log in to your Mac.

Then:

1. **Add pages.** On the Add page, drop in a video of you flipping through a notebook (one page spread at a time, a second or so each), or photos of pages. You can also type an entry.
2. **Check the dates** on the review board at http://localhost:8765. Right (`D`), wrong (`F`, then type the date), not a journal page (`G`).
3. **Open the library** at http://localhost:8765/library.

Want to see it full first? `python3 scripts/demo.py add` fills it with a made-up journal: about 35 entries across six years, categories, stars and some handwritten page photos. `python3 scripts/demo.py remove` takes them all out again and leaves anything you added.

## Morning email

The easiest way is any Gmail account and a Gmail **app password**. No domain or email service needed.

An app password can send and read mail for the whole Gmail account it belongs to, not just this journal. So the safest setup is a spare Gmail account used only for sending (it can send to your main address). The journal only ever sends to the address you put in **Send it to**.

1. On the Gmail account you want to send from, turn on [2-Step Verification](https://myaccount.google.com/signinoptions/two-step-verification).
2. Open [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), type `Journal` as the name and click Create. Copy the 16 letters.
3. In the journal, open **Settings > Morning email**. Fill in where to send it, the Gmail address and the app password, pick a time, then click **Send a test now**.
4. If the test arrives, tick **Send it every morning**.

It's sent from your Mac, so it goes out when the Mac is awake. If the Mac was asleep at that time, it sends when it wakes. Days with nothing from past years are skipped. The app password is stored only on your Mac, in `source/settings.json`. You can revoke it from the same Google page at any time.

## Notes from your phone (optional)

If you keep daily notes in Obsidian, named like `2026-11-25.md`, point the journal at that folder:

```bash
./setup.sh obsidian "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<your vault>/Daily logs"
```

Each day's note becomes an entry, with any embedded photos. For an iCloud folder, macOS asks once whether **JournalSync** may open files in iCloud Drive. Click Allow.

## Put it online (optional)

Open your journal from your phone at `https://<name>.pages.dev`, behind a password.

1. Set a password in **Settings > Password**.
2. Install the tools: `brew install cloudflared node`
3. Run `./setup.sh host <name>`, for example `./setup.sh host maya-journal`. It asks you to log in to a free Cloudflare account the first time.

How it works: the pages.dev site stores nothing. Each visit is passed through a private Cloudflare tunnel to the app on your Mac. When your Mac is asleep, the site says so.

## Reading handwriting

Settings > Page reader lets you choose what reads your pages:

- **macOS Vision**: built in, free, nothing leaves your Mac. This is the default.
- **Ollama**: a vision model running on your Mac, for example `ollama pull qwen2.5vl:3b`.
- **Claude**: your Anthropic API key. Best at messy handwriting and mixed languages.
- **Amazon Bedrock**: a Bedrock API key.

## Record a demo

Click **▶ Demo** in the library, or open `http://localhost:8765/library?demo`. It runs a hands-free tour: it hovers along the year books, pulls one out, opens a month and a day, and turns through the entries. `Space` pauses, `R` restarts, `Esc` stops. Moving the mouse also stops it.

## Where your data lives

Everything you add is in `source/` (your pages, photos, entries, settings, password hash). Built files are in `out/`. Both are in `.gitignore`, so they're never committed. Back up `source/` to keep your journal.

## Stop it

```bash
./setup.sh stop
```

This stops the app, the tunnel and the Obsidian sync. Your pages in `source/` stay where they are.

## License

MIT
