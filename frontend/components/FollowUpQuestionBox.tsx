// Code Here for Follow-Up Questions Box
// Then go to playground to view it

import React from "react";
import { useEffect, useState } from "react";
import {sendChat} from "../lib/chat";
import { match } from "assert";

// const FollowUpQuestionBox: React.FC = () => {
//   return <div>Hello! You can see me? Right?</div>;
// };

export type FollowUpQuestionBoxProps = {
  lastAiMessage: string | null; //stores last message from AI
  onOptionClick:(question: string) => void; //the option clicked by the user

}

export default function FollowUpQuestionBox ({
  lastAiMessage,
  onOptionClick,
}: FollowUpQuestionBoxProps){
  const [options, setOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string|null>(null);

  useEffect(() => {
    //don't create follow-up questions if the AI hasn't said anything
    if(!lastAiMessage || lastAiMessage.trim().length === 0){
      setOptions([]);
      setLoading(false);
      setError(null);
      return;
    }
    
    async function fetchOptions(){
     //assuming options will load
      setLoading(true);
      setError(null);

      try{
        //building a prompt for AI because it will not ramble on about topic 
        // being discussed but instead come up with related questions
        const prompt =
        "You are a helpful assistant for a statistics student.\n" +
        "The student is chatting with you about a problem.\n" +
        "Here is the last thing you said to the student:\n\n" +
        lastAiMessage +
        "\n\nBased on this, generate 3 follow-up questions " +
        "the student might ask next. Return them as a numbered list.";

        const reply = await sendChat(prompt); //how chatbox communicates to backend AI
        //will break up each question
        const lines = reply.split("\n");
        const parsed: string[] = [];
        //will go through the line, if the line is not trimmed, continue
        for(let line of lines){
          const trimmed = line.trim();
          if (!trimmed) continue;
          //this will remove each number separation for the questions
          const findNumber = trimmed.match(/^[0-9]+[.)\-:\s]+(.*)$/);
          if(!findNumber) continue;
          const text = findNumber[1].trim();
          if(text){
            parsed.push(text);
          }
        }
        //if parsing failed, the whole line will become one option
        if(parsed.length === 0){
          setOptions([reply.trim()]);
          //keep only first 3 options
        } else{
          setOptions(parsed.slice(0,3));
        }
      } catch (e){
        //error messages depending on which
        console.error("Error generating follow-up question(s):", e);
        setError("Could not load follow-up questions.");
        setOptions([]);
      } finally{
        setLoading(false);
      }
    } fetchOptions();
}, [lastAiMessage]);
//don't return anything if no AI response EXCEPT the header
if(!lastAiMessage||lastAiMessage.trim().length===0){
  return (
    <div className="mt-4 border-t border-gray-200 pt-3">
      <div className="mb-2 text-sm font-semibold text-gray-900">
        Follow-up Questions
      </div>
      <div className="text-xs text-gray-500">
        Ask a question in the chat and wait for the AI to respond to see
        suggested follow-up questions here.
      </div>
    </div>
  );
}
return(
  <div className="mt-4 border-t border-gray-200 pt-3">
    <div className="mb-2 text-sm font-semibold text-gray-900">
      Follow-up Questions
    </div>
    {loading &&(
      <div className="text-xs text-gray-500">Generating options...</div>
    )}
    {error && (
      <div className="text-xs text-red-600 mb-2">{error}</div>
    )}
    {!loading && !error && options.length > 0 &&(
      <div className="flex flex-wrap gap-2">
        {options.map((q, idx) =>(
          <button
          key={idx}
          type="button"
          className="text-xs px-3 py-1 rounded-full border border-gray-300 bg-white hover:bg-gray-100 transition"
          onClick={()=>onOptionClick(q)}>
            {q}
          </button>
        ))}
      </div>
    )}
    </div>
    );
  }
