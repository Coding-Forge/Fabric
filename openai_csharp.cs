using System;
using Azure;
using Azure.AI.OpenAI;

class Program
{
    static void Main(string[] args)
    {
        // Replace these with your service-specific values
        string endpoint = "https://demomeai.openai.azure.com/openai/deployments/text-embedding-ada-002/embeddings?api-version=2023-05-15";
        string apiKey = "6a00f8a0a6744aae810ab018a6c6b276";
        string deploymentId = "text-embedding-ada-002";

        // Authenticate the client using the API key
        var credential = new AzureKeyCredential(apiKey);
        var client = new AzureOpenAIClient(new Uri(endpoint), credential);

        // Create the embeddings
        var response = client.GetEmbeddings(deploymentId, new EmbeddingsOptions
        {
            Input = new[] { "Please provide me with something to do so I can share this with my customer" }
        });

        // Output the embeddings
        foreach (var embedding in response.Value.Data)
        {
            Console.WriteLine(string.Join(", ", embedding.Embedding));
        }
    }
}
