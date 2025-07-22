# ruff: noqa: T201
import transformers

chat_tokenizer_dir = "./"

tokenizer = transformers.AutoTokenizer.from_pretrained(chat_tokenizer_dir, trust_remote_code=True)

result = tokenizer.encode(input("Enter the text to calculate the number of tokens: "))
print(result)
