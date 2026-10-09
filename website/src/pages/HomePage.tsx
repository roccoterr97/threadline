import { FinalCall } from '../components/home/FinalCall';
import { Hero } from '../components/home/Hero';
import { Promises } from '../components/home/Promises';
import { Story } from '../components/home/Story';
import { usePageTitle } from '../lib/usePageTitle';

/** The front page: what Threadline is, in as few words as it takes, across the full width. */
export function HomePage() {
  usePageTitle(null);
  return (
    <div className="site-container">
      <Hero />
      <Story />
      <Promises />
      <FinalCall />
    </div>
  );
}
