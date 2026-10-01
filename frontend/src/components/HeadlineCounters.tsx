import * as copy from '../copy/en';
import {
  COUNTER_KEYS,
  counterFilters,
  isCounterShown,
  type CounterKey,
  type PeopleCounters,
} from '../domain/counters';
import { writePeopleView, type PeopleView } from '../domain/peopleView';
import { CounterCard } from './CounterCard';

interface HeadlineCountersProps {
  counters: PeopleCounters;
  /** The view on screen now: marks the counter being shown and keeps the sort. */
  view: PeopleView;
}

/**
 * The five headline numbers. Each one opens exactly the people it counts,
 * clearing every other filter but keeping the chosen order.
 */
export function HeadlineCounters({ counters, view }: HeadlineCountersProps) {
  const linkFor = (key: CounterKey) =>
    `?${writePeopleView({ ...counterFilters(key), sort: view.sort }).toString()}`;

  return (
    <ul
      aria-label={copy.home.countersLabel}
      className="grid list-none grid-cols-2 gap-3 p-0 lg:grid-cols-5"
    >
      {COUNTER_KEYS.map((key) => (
        <CounterCard
          key={key}
          label={copy.home.counters[key]}
          value={counters[key]}
          to={linkFor(key)}
          isShown={isCounterShown(key, view)}
        />
      ))}
    </ul>
  );
}
