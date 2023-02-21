The Video Game Valley Compendium
--------------------------------

The Video Game Valley is a mostly-daily livestream hosted by Filmcow on YouTube
which features retro games on real hardware. There are over 1800 streams in the
[playlist](https://www.youtube.com/playlist?list=PLI6HmVcz0NXquDc4QenBMxidVeFue6E08)
at the time of writing

It is hard to search large playlists on YouTube

It is difficult to determine when a given video in a YouTube playlist aired

It is impossible to author/share custom notes for videos in YouTube playlists

The VGV Compendium seeks to address these problems. At a high level, it uses
the official YouTube Data API v3 to load all videos in a YouTube playlist and
show them in a single webpage:

- Playlist items are cached for 30 minutes to reduce compute time and page-load latency
- Simple client-side text filtering is available for browsers with Javascript enabled,
  along with a light/dark theme toggle
- Designed to work with free tier of standard Google Appengine;
  very low compute/network/storage needs
- 'Admin' users are able to save custom notes for videos. Admin status is based on
  Appengine IAM roles but this hasn't been tested with multiple users yet
- Has rudimentary support for some dynamic kinds of notes
- Saves edit history of notes including email address of authors, but hasn't been
  tested in a true multi-author setting yet
- Edit history w/ email addresses redacted are visible to all users
- Supports CSV export as a form of backup/extensibility
- No cookies/tracking beyond whatever Appengine uses to track logins
- Custom notes can be used to track significant events, or capture more detail than the
  video title. It's completely up to you!

Future ideas:
- Might make sense to eventually allow all users to edit, but admins can see author emails and
  block abusive accounts?
- Do more interesting kinds of custom analyses? Longest time between certain kinds of events,
  longest streak of a given event in a row, could look for anomalies in the custom notes, etc.

I'm publishing this to help remove myself as a single point of failure. Hopefully it's easy enough
to adapt to other large YouTube playlists/communities if they want to benefit from this project too
