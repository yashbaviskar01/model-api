import json
import os
from langchain_openai import ChatOpenAI
import requests
from json import dumps, loads
from dotenv import load_dotenv
from langchain.schema.output_parser import StrOutputParser
from langchain.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate,
    ChatPromptTemplate,
)
from app.modules.embeddings import handle_embeddings
from langchain.schema.runnable import RunnablePassthrough
from langchain.load import dumps, loads
from app.utils.utility_functions import Utils

load_dotenv()

CODA_LLM_MODEL = os.getenv("FINAL_ANSWER_MODEL")

class GenerateChat:
    def __init__(self):
        self.utils = Utils()
        self.vector_store = handle_embeddings()
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.llm = ChatOpenAI(
            model=CODA_LLM_MODEL, api_key=self.api_key, temperature=0
        )

    def reciprocal_rank_fusion(self, results: list[list], k=60):
        fused_scores = {}
        for docs in results:
            for rank, doc in enumerate(docs):
                doc_str = dumps(doc)
                if doc_str not in fused_scores:
                    fused_scores[doc_str] = 0
                fused_scores[doc_str] += 1 / (rank + k)

        reranked_results = [
            (loads(doc), score)
            for doc, score in sorted(
                fused_scores.items(), key=lambda x: x[1], reverse=True
            )
        ]
        return reranked_results

    def invoke_query(self, query):
        print("index >>", self.vector_store.index_name)

        retriever = self.vector_store.vectorstore.as_retriever(
            search_type="mmr", search_kwargs={"k": 10, "fetch_k": 100}
        )

        prompt = ChatPromptTemplate(
            input_variables=["original_query"],
            messages=[
                SystemMessagePromptTemplate(
                    prompt=PromptTemplate(
                        input_variables=[],
                        template="You are a helpful assistant that generates multiple search queries based on a single input query.",
                    )
                ),
                HumanMessagePromptTemplate(
                    prompt=PromptTemplate(
                        input_variables=["original_query"],
                        template="Generate multiple search queries related to: {question} \n OUTPUT (2 queries):",
                    )
                ),
            ],
        )
        generate_queries = (
            prompt | self.llm | StrOutputParser() | (lambda x: x.split("\n"))
        )
        # print(f"queries>>>>>>>{generate_queries.invoke(query)}")

        ragfusion_chain = (
            generate_queries | retriever.map() | self.reciprocal_rank_fusion
        )
        # print(f"chaining>>>>> {ragfusion_chain.invoke(query)}")

        template = """
                    Answer the question based on the following context:
                    {context}
 
                    Instructions:
                    - Analyze both the question and context carefully.
                    - Provide direct, conversational answers without mentioning the context itself.
                    - Connect ideas from different parts of the context when reasoning is needed.
                    - Make logical inferences based only on what's in the context.
                    - If information is missing to answer the question directly, say so naturally.
                    - Use a friendly, helpful tone as if having a natural conversation.
                    - Keep answers concise but complete.
                    - Focus on what you do know rather than what you don’t know.
                    ## output format:
                    - Always return the final output in Markdown format without adding anything extra, including unnecessary code block markers (```). Maintain clear formatting for readability, using elements like bold, italics, lists, while preserving the original structure of the data.
 
                    Question: {query}
                    """

        prompt = ChatPromptTemplate.from_template(template)

        full_rag_fusion_chain = (
            {"context": ragfusion_chain, "query": RunnablePassthrough()}
            | prompt
            | self.llm
            | StrOutputParser()
        )

        handbook_ans = full_rag_fusion_chain.invoke({"question": query})
        print("handbook answer>>> ", handbook_ans)
        return handbook_ans

    def answer_question_with_rag_fusion(self, query):
        chain = self.invoke_query(query)
        return chain
