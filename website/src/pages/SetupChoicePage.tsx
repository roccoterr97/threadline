import { useParams } from 'react-router-dom';
import { OptionButtons } from '../components/setup/OptionButtons';
import { WizardFrame } from '../components/setup/WizardFrame';
import * as copy from '../copy/en';
import { usePageTitle } from '../lib/usePageTitle';
import { setChoice } from '../setup/progress';
import { useWizard } from '../setup/useWizard';
import { NoSuchScreen } from './NoSuchScreen';

/** A part's opening question, such as which mailbox is read. */
export function SetupChoicePage() {
  const { choiceId } = useParams();
  const place = useWizard('choice', choiceId);
  const screen = place?.screen.kind === 'choice' ? place.screen : null;
  usePageTitle(screen?.choice.question ?? copy.wizard.noSuchScreen);
  if (place === null || screen === null) return <NoSuchScreen />;
  const answer = place.progress.choices[screen.choice.id];
  return (
    <WizardFrame
      eyebrow={screen.part.title}
      title={screen.choice.question}
      progress={place.position}
      back={place.back}
      next={place.next === null ? null : { label: copy.wizard.next, to: place.next, disabled: answer === undefined }}
    >
      <OptionButtons
        question={screen.choice.question}
        options={screen.choice.options}
        value={answer}
        onChange={(id) => setChoice(screen.choice.id, id)}
      />
    </WizardFrame>
  );
}
