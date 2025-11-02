import React from 'react';

type QuestionBoxProps = {
  question: string;
  subtitle?: string;
  className?: string;
};

export default function QuestionBox({ question, subtitle, className = '' }: QuestionBoxProps) {
  return (
    <div className={`${className}`}>
      <h2 className="text-lg font-semibold text-gray-900 mb-2">{question}</h2>
      {subtitle ? (
        <p className="text-sm text-gray-600">{subtitle}</p>
      ) : null}
    </div>
  );
}
