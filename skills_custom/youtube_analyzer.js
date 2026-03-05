/**
 * YouTube Analyzer — Agent ANALYST
 * Analyse les vidéos crypto performantes sur YouTube
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

// Configuration
const API_KEY = process.env.YOUTUBE_API_KEY;
const WORKSPACE = '/home/node/.openclaw/workspace';
const REPORTS_DIR = `${WORKSPACE}/agents/analyst/reports`;
const REFERENCES_DIR = `${WORKSPACE}/agents/analyst/references`;

// Chaînes crypto à surveiller (IDs YouTube)
const CHANNELS_TO_WATCH = {
  // Français
  'hasheur': 'UCt1gvKG4e8ez3GdD9sNx_yg',
  'cryptoast': 'UCmAt-ax8X1rT3kgWcBOqvZA',
  'journalducoin': 'UCkKD0ik3HOtRwZTlEoqsJKg',
  // Anglais
  'coinbureau': 'UCqK_GSMbpiV8spgD3ZGloSw',
  'altcoindaily': 'UCbLhGKVY-bJPcawebgtNfbw',
  'cryptobanter': 'UCNFqqLPkYBJmVzN-fKMWWUw'
};

// Mots-clés de recherche
const SEARCH_KEYWORDS = [
  'bitcoin actualité',
  'crypto news today',
  'ethereum analyse',
  'altcoin 2026',
  'bull run crypto',
  'bitcoin price prediction'
];

/**
 * Appel API YouTube
 */
function youtubeAPI(endpoint, params) {
  return new Promise((resolve, reject) => {
    const queryString = new URLSearchParams({
      ...params,
      key: API_KEY
    }).toString();
    
    const url = `https://www.googleapis.com/youtube/v3/${endpoint}?${queryString}`;
    
    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

/**
 * Rechercher les vidéos récentes par mot-clé
 */
async function searchVideos(keyword, maxResults = 10) {
  const response = await youtubeAPI('search', {
    part: 'snippet',
    q: keyword,
    type: 'video',
    order: 'viewCount',
    publishedAfter: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
    maxResults,
    relevanceLanguage: 'fr'
  });
  
  return response.items || [];
}

/**
 * Obtenir les statistiques d'une vidéo
 */
async function getVideoStats(videoIds) {
  if (!videoIds.length) return [];
  
  const response = await youtubeAPI('videos', {
    part: 'statistics,snippet,contentDetails',
    id: videoIds.join(',')
  });
  
  return response.items || [];
}

/**
 * Analyser les vidéos d'une chaîne
 */
async function analyzeChannel(channelId, channelName) {
  console.log(`[analyst] Analyse de ${channelName}...`);
  
  const response = await youtubeAPI('search', {
    part: 'snippet',
    channelId,
    type: 'video',
    order: 'date',
    maxResults: 5
  });
  
  if (!response.items) return [];
  
  const videoIds = response.items.map(v => v.id.videoId);
  const stats = await getVideoStats(videoIds);
  
  return stats.map(video => ({
    id: video.id,
    title: video.snippet.title,
    channel: channelName,
    publishedAt: video.snippet.publishedAt,
    thumbnail: video.snippet.thumbnails.high?.url || video.snippet.thumbnails.default?.url,
    views: parseInt(video.statistics.viewCount || 0),
    likes: parseInt(video.statistics.likeCount || 0),
    comments: parseInt(video.statistics.commentCount || 0),
    duration: video.contentDetails.duration,
    url: `https://youtube.com/watch?v=${video.id}`
  }));
}

/**
 * Générer le rapport quotidien
 */
async function generateDailyReport() {
  console.log('=== YOUTUBE ANALYZER — Daily Report ===');
  console.log(`Date: ${new Date().toISOString()}`);
  
  if (!API_KEY) {
    console.error('[analyst] ❌ YOUTUBE_API_KEY non définie');
    return;
  }
  
  const allVideos = [];
  
  // Analyser les chaînes surveillées
  for (const [name, id] of Object.entries(CHANNELS_TO_WATCH)) {
    try {
      const videos = await analyzeChannel(id, name);
      allVideos.push(...videos);
      await new Promise(r => setTimeout(r, 200)); // Rate limiting
    } catch (err) {
      console.error(`[analyst] Erreur ${name}:`, err.message);
    }
  }
  
  // Rechercher par mots-clés (top 2 pour économiser le quota)
  for (const keyword of SEARCH_KEYWORDS.slice(0, 2)) {
    try {
      console.log(`[analyst] Recherche: "${keyword}"`);
      const searchResults = await searchVideos(keyword, 5);
      const videoIds = searchResults.map(v => v.id.videoId);
      const stats = await getVideoStats(videoIds);
      
      const videos = stats.map(video => ({
        id: video.id,
        title: video.snippet.title,
        channel: video.snippet.channelTitle,
        publishedAt: video.snippet.publishedAt,
        thumbnail: video.snippet.thumbnails.high?.url,
        views: parseInt(video.statistics.viewCount || 0),
        likes: parseInt(video.statistics.likeCount || 0),
        comments: parseInt(video.statistics.commentCount || 0),
        duration: video.contentDetails.duration,
        url: `https://youtube.com/watch?v=${video.id}`,
        keyword
      }));
      
      allVideos.push(...videos);
      await new Promise(r => setTimeout(r, 200));
    } catch (err) {
      console.error(`[analyst] Erreur recherche "${keyword}":`, err.message);
    }
  }
  
  // Dédupliquer par ID
  const uniqueVideos = [...new Map(allVideos.map(v => [v.id, v])).values()];
  
  // Trier par vues
  uniqueVideos.sort((a, b) => b.views - a.views);
  
  // Top 10
  const topVideos = uniqueVideos.slice(0, 10);
  
  // Générer le rapport
  const report = {
    date: new Date().toISOString().split('T')[0],
    generated_at: new Date().toISOString(),
    summary: {
      total_videos_analyzed: uniqueVideos.length,
      channels_monitored: Object.keys(CHANNELS_TO_WATCH).length,
      keywords_searched: 2
    },
    top_videos: topVideos,
    trending_topics: extractTopics(topVideos),
    insights: generateInsights(topVideos)
  };
  
  // Sauvegarder
  const filename = `${REPORTS_DIR}/daily/${report.date}.json`;
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  fs.writeFileSync(filename, JSON.stringify(report, null, 2));
  console.log(`[analyst] ✅ Rapport sauvegardé: ${filename}`);
  
  // Sauvegarder les références (miniatures performantes)
  saveReferences(topVideos.slice(0, 5));
  
  // Afficher résumé
  console.log('\n📊 TOP 5 VIDÉOS DU JOUR:');
  topVideos.slice(0, 5).forEach((v, i) => {
    console.log(`${i + 1}. ${v.title}`);
    console.log(`   👁️ ${v.views.toLocaleString()} vues | 👍 ${v.likes.toLocaleString()} likes`);
    console.log(`   📺 ${v.channel} | ${v.url}`);
  });
  
  return report;
}

/**
 * Extraire les sujets tendance des titres
 */
function extractTopics(videos) {
  const words = {};
  const stopWords = ['the', 'a', 'an', 'is', 'are', 'to', 'of', 'and', 'in', 'for', 'on', 'le', 'la', 'les', 'de', 'du', 'des', 'et', 'en', 'un', 'une'];
  
  videos.forEach(v => {
    v.title.toLowerCase()
      .replace(/[^\w\s]/g, '')
      .split(/\s+/)
      .filter(w => w.length > 3 && !stopWords.includes(w))
      .forEach(word => {
        words[word] = (words[word] || 0) + 1;
      });
  });
  
  return Object.entries(words)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([word, count]) => ({ word, count }));
}

/**
 * Générer des insights automatiques
 */
function generateInsights(videos) {
  const insights = [];
  
  if (videos.length === 0) return insights;
  
  // Durée moyenne
  const avgViews = videos.reduce((s, v) => s + v.views, 0) / videos.length;
  insights.push(`Moyenne de vues: ${Math.round(avgViews).toLocaleString()}`);
  
  // Meilleur ratio likes/vues
  const bestEngagement = videos.reduce((best, v) => {
    const ratio = v.views > 0 ? v.likes / v.views : 0;
    return ratio > best.ratio ? { video: v, ratio } : best;
  }, { ratio: 0 });
  
  if (bestEngagement.video) {
    insights.push(`Meilleur engagement: "${bestEngagement.video.title.slice(0, 50)}..." (${(bestEngagement.ratio * 100).toFixed(1)}%)`);
  }
  
  return insights;
}

/**
 * Sauvegarder les références pour l'équipe créative
 */
function saveReferences(topVideos) {
  const refsFile = `${REFERENCES_DIR}/top_performers.json`;
  
  let existing = [];
  try {
    existing = JSON.parse(fs.readFileSync(refsFile, 'utf8'));
  } catch (e) {
    // Fichier n'existe pas encore
  }
  
  // Ajouter les nouvelles références
  const newRefs = topVideos.map(v => ({
    added_at: new Date().toISOString(),
    title: v.title,
    channel: v.channel,
    thumbnail: v.thumbnail,
    views: v.views,
    url: v.url
  }));
  
  // Garder les 50 dernières
  const allRefs = [...newRefs, ...existing].slice(0, 50);
  
  fs.mkdirSync(path.dirname(refsFile), { recursive: true });
  fs.writeFileSync(refsFile, JSON.stringify(allRefs, null, 2));
  console.log(`[analyst] ✅ ${newRefs.length} références sauvegardées`);
}

// Exécution
generateDailyReport().catch(console.error);
