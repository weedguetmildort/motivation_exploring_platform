type DisclaimerProps = {
  groupName: string;
  institution: string;
  contactEmail: string;
  supervisor: string;
};

export default function Disclaimer({
  groupName,
  institution,
  contactEmail,
  supervisor,
}: DisclaimerProps) {
  return (
    <div className="text-sm text-gray-600">
      <p>
        This website is part of a research study conducted by the {groupName} at{" "}
        {institution} under the supervision of {supervisor}.
      </p>
      <p className="mt-2">
        Participation in this study is voluntary. You may choose not to
        participate or stop at any time without penalty.
      </p>
      <p className="mt-2">
        If you have any questions, concerns, or experience any issues while
        using this site, please contact us at{" "}
        <a href={`mailto:${contactEmail}`} className="underline">
          {contactEmail}
        </a>
        .
      </p>
    </div>
  );
}
