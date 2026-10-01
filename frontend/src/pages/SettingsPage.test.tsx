import { screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchCategories } from '../api/categories';
import {
  addCategory,
  removeCategory,
  RemovalOutcome,
  saveCategoryOrder,
  showCategoryAgain,
  updateCategory,
} from '../api/categoryEdits';
import { fetchCategorySuggestions } from '../api/categorySuggestions';
import * as copy from '../copy/en';
import { DataUnavailableError, RefusalReason, RefusedError } from '../lib/errors';
import { expectNoAxeViolations } from '../test/axe';
import { category, NOW, sampleCategories, withArchived } from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import type { CategorySuggestion } from '../types/database';
import { SettingsPage } from './SettingsPage';

vi.mock('../api/categories', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/categories')>()),
  fetchCategories: vi.fn(),
}));

vi.mock('../api/categorySuggestions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/categorySuggestions')>()),
  fetchCategorySuggestions: vi.fn(),
}));

vi.mock('../api/categoryEdits', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/categoryEdits')>()),
  addCategory: vi.fn(),
  updateCategory: vi.fn(),
  saveCategoryOrder: vi.fn(),
  removeCategory: vi.fn(),
  showCategoryAgain: vi.fn(),
}));

const fetchCategoriesMock = vi.mocked(fetchCategories);
const fetchSuggestionsMock = vi.mocked(fetchCategorySuggestions);
const addMock = vi.mocked(addCategory);
const updateMock = vi.mocked(updateCategory);
const orderMock = vi.mocked(saveCategoryOrder);
const removeMock = vi.mocked(removeCategory);
const showAgainMock = vi.mocked(showCategoryAgain);

const actions = copy.categorySettings.actions;
const fields = copy.categorySettings.fields;

const MENTOR: CategorySuggestion = {
  key: 'mentor',
  label: 'Mentor',
  group_label: 'Mentors',
  description: 'People who give me advice.',
  colour: 'teal',
};

/** The preset's three, plus one the owner does not have yet. */
const SUGGESTIONS: CategorySuggestion[] = [
  ...sampleCategories
    .filter((c) => c.key !== 'unknown')
    .map(({ key, label, group_label, description, colour }) => ({
      key,
      label,
      group_label,
      description,
      colour,
    })),
  MENTOR,
];

const HUES = ['violet', 'cyan', 'orange', 'pink', 'indigo', 'teal', 'olive', 'brown'] as const;

/** Eight categories in use, one hidden, and the reserved one. */
const FULL = withArchived(
  [
    ...HUES.map((hue, index) =>
      category(`cat_${hue}`, `Cat ${hue}`, `Cats ${hue}`, hue, index + 1),
    ),
    category('spare', 'Spare', 'Spares', 'grey', 90),
    category('unknown', 'Not known', 'Unknown', 'grey', 1000),
  ],
  'spare',
);

/** The list item for one of the owner's categories. */
function rowOf(label: string): HTMLElement {
  return screen.getByRole('button', { name: actions.changeLabel(label) }).closest('li')!;
}

/** The "Add your own" section. */
function addSection(): HTMLElement {
  return screen.getByRole('region', { name: copy.categorySettings.addOwn });
}

async function renderSettings() {
  const result = renderWithProviders(<SettingsPage />);
  await screen.findByRole('region', { name: copy.categorySettings.yours });
  return result;
}

beforeEach(() => {
  fetchCategoriesMock.mockResolvedValue(withArchived(sampleCategories, 'network'));
  fetchSuggestionsMock.mockResolvedValue(SUGGESTIONS);
  addMock.mockResolvedValue(undefined);
  updateMock.mockResolvedValue(undefined);
  orderMock.mockResolvedValue(undefined);
  removeMock.mockResolvedValue(RemovalOutcome.Deleted);
  showAgainMock.mockResolvedValue(undefined);
});

describe('SettingsPage — what it shows', () => {
  it('says what it is loading while it waits', () => {
    fetchCategoriesMock.mockReturnValue(new Promise(() => undefined));
    renderWithProviders(<SettingsPage />);
    expect(screen.getByText(copy.settings.loading)).toBeInTheDocument();
  });

  it('offers a retry when the categories cannot be loaded', async () => {
    fetchCategoriesMock.mockRejectedValue(new DataUnavailableError('categories.list'));
    renderWithProviders(<SettingsPage />);
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();
  });

  it('lists the categories in use, the hidden ones and the new suggestions', async () => {
    await renderSettings();
    const yours = screen.getByRole('region', { name: copy.categorySettings.yours });
    const items = within(yours).getAllByRole('listitem');
    expect(items.map((item) => item.querySelector('p')?.textContent)).toEqual([
      'Startup · Startups',
      'Investor · Investors',
      'Not known',
    ]);

    const hidden = screen.getByRole('region', { name: copy.categorySettings.hidden });
    expect(within(hidden).getByText('Network')).toBeInTheDocument();

    const suggestions = screen.getByRole('region', { name: copy.categorySettings.suggestions });
    expect(within(suggestions).getAllByRole('button').map((b) => b.textContent)).toEqual([
      actions.addSuggestion('Mentor'),
    ]);
  });

  it('shows "not known" but offers no way to change, move or remove it', async () => {
    await renderSettings();
    expect(screen.getByText(copy.categorySettings.reservedNote)).toBeInTheDocument();
    for (const name of [
      actions.changeLabel('Not known'),
      actions.moveUpLabel('Not known'),
      actions.removeLabel('Not known'),
    ]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
  });

  it('leaves the hidden section out when nothing is hidden', async () => {
    fetchCategoriesMock.mockResolvedValue(sampleCategories);
    await renderSettings();
    expect(
      screen.queryByRole('region', { name: copy.categorySettings.hidden }),
    ).not.toBeInTheDocument();
  });
});

describe('SettingsPage — adding', () => {
  it('adds a suggestion with one tap, after the other categories', async () => {
    const { user } = await renderSettings();
    await user.click(screen.getByRole('button', { name: actions.addSuggestion('Mentor') }));

    expect(addMock).toHaveBeenCalledWith({ ...MENTOR, sort_order: 40 });
    expect(await screen.findByText(copy.categorySettings.done.added('Mentor'))).toBeInTheDocument();
  });

  it('gives a suggestion a free colour when a category in use already has its own', async () => {
    fetchSuggestionsMock.mockResolvedValue([{ ...MENTOR, colour: 'violet' }]);
    const { user } = await renderSettings();
    await user.click(screen.getByRole('button', { name: actions.addSuggestion('Mentor') }));

    expect(addMock).toHaveBeenCalledWith({ ...MENTOR, colour: 'orange', sort_order: 40 });
  });

  it('starts "Add your own" on a colour nobody uses, and follows it until one is picked', async () => {
    const { user } = await renderSettings();
    const form = within(addSection());
    expect(form.getByRole('radio', { name: 'Orange' })).toBeChecked();

    // Mentor is added in orange somewhere else on the page.
    fetchCategoriesMock.mockResolvedValue([
      ...withArchived(sampleCategories, 'network'),
      { ...MENTOR, colour: 'orange', sort_order: 40, archived_at: null },
    ]);
    await user.click(screen.getByRole('button', { name: actions.addSuggestion('Mentor') }));
    await waitFor(() => {
      expect(form.getByRole('radio', { name: 'Pink' })).toBeChecked();
    });

    await user.click(form.getByRole('radio', { name: 'Olive' }));
    expect(form.getByRole('radio', { name: 'Olive' })).toBeChecked();
  });

  it('adds a category of the owner\'s own, with a key made from its name', async () => {
    const { user } = await renderSettings();
    const form = within(addSection());

    await user.type(form.getByLabelText(fields.name), 'Key account');
    expect(form.getByLabelText(fields.groupName)).toHaveValue('Key accounts');
    await user.type(form.getByLabelText(fields.description), 'Our biggest customers.');
    await user.click(form.getByRole('radio', { name: 'Teal' }));
    await user.click(form.getByRole('button', { name: actions.add }));

    expect(addMock).toHaveBeenCalledWith({
      key: 'key_account',
      label: 'Key account',
      group_label: 'Key accounts',
      description: 'Our biggest customers.',
      colour: 'teal',
      sort_order: 40,
    });
    await waitFor(() => {
      expect(form.getByLabelText(fields.name)).toHaveValue('');
    });
  });

  it('asks for what is missing instead of saving', async () => {
    const { user } = await renderSettings();
    const form = within(addSection());
    await user.type(form.getByLabelText(fields.name), 'Customer');
    await user.click(form.getByRole('button', { name: actions.add }));

    expect(form.getByRole('alert')).toHaveTextContent(
      copy.categoryDraftProblems.missing_description,
    );
    expect(addMock).not.toHaveBeenCalled();
  });

  it('marks the field at fault and moves the keyboard to it', async () => {
    const { user } = await renderSettings();
    const form = within(addSection());
    await user.type(form.getByLabelText(fields.name), 'Customer');
    await user.click(form.getByRole('button', { name: actions.add }));

    const description = form.getByLabelText(fields.description);
    expect(description).toHaveAttribute('aria-invalid', 'true');
    expect(description).toHaveAccessibleDescription(copy.categoryDraftProblems.missing_description);
    expect(description).toHaveFocus();
    expect(form.getByLabelText(fields.name)).not.toHaveAttribute('aria-invalid');
  });

  it('counts the characters and says when a name is full', async () => {
    const { user } = await renderSettings();
    const form = within(addSection());
    const length = copy.categorySettings.length;
    const name = form.getByLabelText(fields.name);
    await user.type(name, 'Key account');
    expect(name).toHaveAccessibleDescription(length.count(11, 40));
    expect(form.queryByText(length.atLimit(40))).not.toBeInTheDocument();

    await user.clear(name);
    await user.type(name, 'x'.repeat(45));
    expect(name).toHaveValue('x'.repeat(40));
    expect(form.getAllByText(length.atLimit(40))).toHaveLength(2);
  });

  it('keeps a long name\'s suggested group name within the limit', async () => {
    const { user } = await renderSettings();
    const form = within(addSection());
    await user.type(form.getByLabelText(fields.name), 'x'.repeat(40));
    await user.type(form.getByLabelText(fields.description), 'Long ones.');
    expect(form.getByLabelText(fields.groupName)).toHaveValue('x'.repeat(40));
    await user.click(form.getByRole('button', { name: actions.add }));

    expect(addMock).toHaveBeenCalledWith(expect.objectContaining({ group_label: 'x'.repeat(40) }));
  });

  it('turns down a name another category already has, whatever its case', async () => {
    const { user } = await renderSettings();
    const form = within(addSection());
    await user.type(form.getByLabelText(fields.name), 'startup');
    await user.type(form.getByLabelText(fields.description), 'Founders.');
    await user.click(form.getByRole('button', { name: actions.add }));

    expect(form.getByRole('alert')).toHaveTextContent(copy.categoryDraftProblems.duplicate_name);
    expect(addMock).not.toHaveBeenCalled();
  });

  it('turns down a group name a hidden category already has', async () => {
    const { user } = await renderSettings();
    const form = within(addSection());
    await user.type(form.getByLabelText(fields.name), 'Contact');
    await user.clear(form.getByLabelText(fields.groupName));
    await user.type(form.getByLabelText(fields.groupName), 'network');
    await user.type(form.getByLabelText(fields.description), 'People I know.');
    await user.click(form.getByRole('button', { name: actions.add }));

    expect(form.getByRole('alert')).toHaveTextContent(
      copy.categoryDraftProblems.duplicate_group_name,
    );
    expect(addMock).not.toHaveBeenCalled();
  });

  it('switches adding and "show again" off once eight categories are in use', async () => {
    fetchCategoriesMock.mockResolvedValue(FULL);
    fetchSuggestionsMock.mockResolvedValue([MENTOR]);
    await renderSettings();

    expect(screen.getAllByText(copy.categorySettings.limitReached).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: actions.addSuggestion('Mentor') })).toBeDisabled();
    expect(within(addSection()).getByRole('button', { name: actions.add })).toBeDisabled();
    expect(screen.getByRole('button', { name: actions.showAgainLabel('Spare') })).toBeDisabled();
  });

  it('explains a refusal from the database in plain words', async () => {
    addMock.mockRejectedValue(new RefusedError(RefusalReason.BreaksRule, 'categories.add'));
    const { user } = await renderSettings();
    await user.click(screen.getByRole('button', { name: actions.addSuggestion('Mentor') }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      copy.categorySettings.failed.breaksRule,
    );
  });
});

describe('SettingsPage — changing', () => {
  it('renames a category and keeps its key', async () => {
    const { user } = await renderSettings();
    await user.click(screen.getByRole('button', { name: actions.changeLabel('Startup') }));
    const row = within(screen.getByRole('button', { name: actions.save }).closest('li')!);

    await user.clear(row.getByLabelText(fields.name));
    await user.type(row.getByLabelText(fields.name), 'Founder');
    await user.click(row.getByRole('button', { name: actions.save }));

    expect(updateMock).toHaveBeenCalledWith('startup', {
      label: 'Founder',
      group_label: 'Startups',
      description: sampleCategories[0]!.description,
      colour: 'violet',
    });
    expect(
      await screen.findByText(copy.categorySettings.done.saved('Founder')),
    ).toBeInTheDocument();
  });

  it('lets a category keep its own name but not take another one\'s', async () => {
    const { user } = await renderSettings();
    await user.click(screen.getByRole('button', { name: actions.changeLabel('Startup') }));
    const row = within(screen.getByRole('button', { name: actions.save }).closest('li')!);

    await user.clear(row.getByLabelText(fields.name));
    await user.type(row.getByLabelText(fields.name), 'INVESTOR');
    await user.click(row.getByRole('button', { name: actions.save }));
    expect(row.getByRole('alert')).toHaveTextContent(copy.categoryDraftProblems.duplicate_name);
    expect(updateMock).not.toHaveBeenCalled();

    await user.clear(row.getByLabelText(fields.name));
    await user.type(row.getByLabelText(fields.name), 'STARTUP');
    await user.click(row.getByRole('button', { name: actions.save }));
    expect(updateMock).toHaveBeenCalledWith('startup', expect.objectContaining({ label: 'STARTUP' }));
  });

  it('moves a category up and saves the new order', async () => {
    const { user } = await renderSettings();
    expect(screen.getByRole('button', { name: actions.moveUpLabel('Startup') })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: actions.moveUpLabel('Investor') }));

    expect(orderMock).toHaveBeenCalledWith([
      { key: 'vc', sort_order: 10 },
      { key: 'startup', sort_order: 20 },
    ]);
  });

  it('keeps the keyboard on the moved row once the new order is in', async () => {
    const [startup, vc, network, unknown] = sampleCategories;
    fetchCategoriesMock.mockResolvedValue(sampleCategories);
    orderMock.mockImplementation(() => {
      fetchCategoriesMock.mockResolvedValue([
        { ...startup!, sort_order: 10 },
        { ...network!, sort_order: 20 },
        { ...vc!, sort_order: 30 },
        unknown!,
      ]);
      return Promise.resolve();
    });
    const { user } = await renderSettings();

    await user.click(screen.getByRole('button', { name: actions.moveUpLabel('Network') }));

    expect(await screen.findByText(copy.categorySettings.done.moved('Network'))).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: actions.moveUpLabel('Network') })).toHaveFocus();
    });
    const items = within(screen.getByRole('region', { name: copy.categorySettings.yours }));
    expect(items.getAllByRole('listitem')[1]).toHaveTextContent('Network');
  });

  it('moves the keyboard to the other move button when a row reaches the end', async () => {
    const [startup, vc, , unknown] = sampleCategories;
    orderMock.mockImplementation(() => {
      fetchCategoriesMock.mockResolvedValue([
        { ...vc!, sort_order: 10 },
        { ...startup!, sort_order: 20 },
        unknown!,
      ]);
      return Promise.resolve();
    });
    const { user } = await renderSettings();

    await user.click(screen.getByRole('button', { name: actions.moveUpLabel('Investor') }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: actions.moveDownLabel('Investor') })).toHaveFocus();
    });
  });

  it('removes a category nobody has', async () => {
    const { user } = await renderSettings();
    const row = within(rowOf('Investor'));
    await user.click(row.getByRole('button', { name: actions.removeLabel('Investor') }));
    expect(removeMock).not.toHaveBeenCalled();
    const question = row.getByRole('group', { name: actions.removeConfirmTitle('Investor') });
    expect(question).toHaveTextContent(actions.removeConfirmBody);
    await user.click(within(question).getByRole('button', { name: actions.removeConfirm }));

    expect(removeMock).toHaveBeenCalledWith('vc', NOW);
    expect(
      await screen.findByText(copy.categorySettings.done.removed('Investor')),
    ).toBeInTheDocument();
  });

  it('says so when a category people still have was hidden instead', async () => {
    removeMock.mockResolvedValue(RemovalOutcome.Archived);
    const { user } = await renderSettings();
    await user.click(screen.getByRole('button', { name: actions.removeLabel('Startup') }));
    await user.click(screen.getByRole('button', { name: actions.removeConfirm }));
    expect(
      await screen.findByText(copy.categorySettings.done.hiddenInstead('Startup')),
    ).toBeInTheDocument();
  });

  it('keeps a category when the owner thinks better of removing it', async () => {
    const { user } = await renderSettings();
    await user.click(screen.getByRole('button', { name: actions.removeLabel('Investor') }));
    await user.click(screen.getByRole('button', { name: actions.removeCancel }));

    expect(removeMock).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: actions.removeLabel('Investor') })).toHaveFocus();
  });

  it('shows a hidden category again', async () => {
    const { user } = await renderSettings();
    await user.click(screen.getByRole('button', { name: actions.showAgainLabel('Network') }));
    expect(showAgainMock).toHaveBeenCalledWith('network');
  });
});

describe('SettingsPage — accessibility', () => {
  it('has no axe violations, with a category open for changing', async () => {
    const { user, container } = await renderSettings();
    await user.click(screen.getByRole('button', { name: actions.changeLabel('Startup') }));
    await expectNoAxeViolations(container);
  });
});
