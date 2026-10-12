import type { Channel } from '../types/database';

interface ChannelIconProps {
  channel: Channel;
}

/** The drawing for each channel, on a 24x24 grid. */
const CHANNEL_PATHS: Record<Channel, string> = {
  linkedin:
    'M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM3 9h4v12H3V9Zm7 0h3.8v1.7h.05c.53-.95 1.83-1.95 3.76-1.95C21.4 8.75 22 11 22 14.1V21h-4v-6.1c0-1.45-.03-3.3-2-3.3-2.01 0-2.32 1.57-2.32 3.2V21h-4V9Z',
  email:
    'M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm1.6 2L12 12.3 19.4 7H4.6ZM20 8.9l-7.4 5.3a1 1 0 0 1-1.2 0L4 8.9V17h16V8.9Z',
  calendar:
    'M8 2a1 1 0 0 1 1 1v1h6V3a1 1 0 1 1 2 0v1h2a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2V3a1 1 0 0 1 1-1ZM5 10v9h14v-9H5Zm2 2h3v3H7v-3Z',
  telegram:
    'M2.6 11.1 20.5 3.7a1 1 0 0 1 1.3 1.2l-3.9 15.2a1 1 0 0 1-1.5.6l-4.6-3.4-2.4 2.3a.6.6 0 0 1-1-.4v-3.9l8.3-7.8-10.2 6.4-3.9-1.3a.8.8 0 0 1 0-1.5Z',
  slack:
    'M9.1 3h2l-.6 5h4l.6-5h2l-.6 5H20v2h-3.7l-.5 4H19v2h-3.4l-.6 5h-2l.6-5h-4l-.6 5h-2l.6-5H4v-2h3.8l.5-4H5V8h3.5l.6-5Zm1.1 7-.5 4h4l.5-4h-4Z',
  teams:
    'M4 3h11a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H9l-4 3v-3H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm15 5h1a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2h-1v3l-4-3h-4a2 2 0 0 1-2-2h7a3 3 0 0 0 3-3V8Z',
};

/**
 * A small picture of the channel.
 *
 * Purely decorative: every place that uses it also prints the channel's name,
 * so the icon is never the only way to tell one channel from another.
 */
export function ChannelIcon({ channel }: ChannelIconProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 24 24"
      className="h-4 w-4 shrink-0 fill-current"
    >
      <path d={CHANNEL_PATHS[channel]} />
    </svg>
  );
}
