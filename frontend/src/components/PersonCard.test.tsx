import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import * as copy from '../copy/en';
import { nameReservedCategory } from '../domain/categories';
import { resolveStatusLabels } from '../domain/vocabulary';
import { NOW, sampleCategories, samplePerson } from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import { fixedClock } from '../lib/clock';
import type { PeopleOverviewRow } from '../types/database';
import { PersonCard } from './PersonCard';

const vocabulary = {
  categories: nameReservedCategory(sampleCategories, copy.values.unknown),
  statusLabels: resolveStatusLabels(undefined, copy.defaultStatusLabels),
};

function renderCard(person: PeopleOverviewRow) {
  renderWithProviders(
    <ul>
      <PersonCard person={person} clock={fixedClock(NOW)} vocabulary={vocabulary} />
    </ul>,
  );
  return within(screen.getByRole('listitem'));
}

describe('PersonCard', () => {
  it.each([
    ['me', 'Your turn'],
    ['them', 'Waiting on them'],
  ] as const)('says what "waiting on %s" means on its own', (waitingOn, words) => {
    const card = renderCard({ ...samplePerson(), waiting_on: waitingOn });
    expect(card.getByText(words)).toBeInTheDocument();
  });

  it('says "not known" once, for the category, and leaves out the unknown role', () => {
    const card = renderCard({
      ...samplePerson(),
      person_type: 'unknown',
      role_title: null,
      organisation_name: null,
    });
    expect(card.getAllByText(copy.values.unknown)).toHaveLength(1);
  });

  it('shows the organisation alone when the role is not known', () => {
    const card = renderCard({ ...samplePerson(), role_title: null, organisation_name: 'Acme' });
    expect(card.getByText('Acme')).toBeInTheDocument();
  });
});
