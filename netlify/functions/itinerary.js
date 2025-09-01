exports.handler = async (event, context) => {
  const headers = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
  };

  // Handle CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  try {
    const pathSegments = event.path.split('/').filter(Boolean);
    const conversationId = pathSegments[pathSegments.length - 1];

    if (event.httpMethod === 'GET') {
      // Get itinerary
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({
          conversation_id: conversationId,
          message: "Itinerary retrieval requires full server deployment. Please use Heroku or Render for complete functionality.",
          itinerary: null
        })
      };
    }

    if (event.httpMethod === 'POST' && event.path.includes('populate-accommodations')) {
      // Populate accommodations
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({
          conversation_id: conversationId,
          message: "Accommodation population requires Agoda API integration. Please use full server deployment.",
          accommodations: []
        })
      };
    }

    return {
      statusCode: 404,
      headers,
      body: JSON.stringify({ error: 'Endpoint not found' })
    };

  } catch (error) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: error.message })
    };
  }
};
