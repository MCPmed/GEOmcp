"""GEO search functionality using NCBI E-Utilities."""

import json
import time
from typing import Dict, Any, List, Optional
import httpx

from .config import get_config


class GEOSearchError(Exception):
    """Exception raised for GEO search errors."""
    pass


class GEOSearchClient:
    """Client for searching GEO database using NCBI E-Utilities."""
    
    def __init__(self):
        self.config = get_config()
        self.base_url = self.config["base_url"]
        self.email = self.config["email"]
        self.api_key = self.config.get("api_key")
        self.retmax = self.config.get("retmax", 20)
        self._last_request_time = 0
    
    def _rate_limit(self):
        """Apply rate limiting to be respectful to NCBI servers."""
        # Without API key: 3 requests per second
        # With API key: 10 requests per second
        min_interval = 0.1 if self.api_key else 0.34
        
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()
    
    def _build_params(self, extra_params: Dict[str, Any]) -> Dict[str, str]:
        """Build request parameters with authentication."""
        params = {"email": self.email, **extra_params}
        if self.api_key:
            params["api_key"] = self.api_key
        return params
    
    async def _esearch(self, db: str, term: str, retmax: int = 20) -> Dict[str, Any]:
        """Perform ESearch query.
        
        Args:
            db: Database to search (gds, geoprofiles, etc.)
            term: Search term
            retmax: Maximum results to return
            
        Returns:
            ESearch response dictionary
        """
        self._rate_limit()
        
        params = self._build_params({
            "db": db,
            "term": term,
            "retmax": retmax,
            "retmode": "json",
        })
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/esearch.fcgi",
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def _esummary(self, db: str, ids: List[str]) -> Dict[str, Any]:
        """Fetch summaries for a list of IDs.
        
        Args:
            db: Database
            ids: List of IDs to summarize
            
        Returns:
            ESummary response dictionary
        """
        if not ids:
            return {"result": {}}
        
        self._rate_limit()
        
        params = self._build_params({
            "db": db,
            "id": ",".join(map(str, ids)),
            "retmode": "json",
        })
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/esummary.fcgi",
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def _efetch(self, db: str, id: str, retmode: str = "xml") -> str:
        """Fetch full records.
        
        Args:
            db: Database
            id: Record ID
            retmode: Return mode (xml, json, etc.)
            
        Returns:
            EFetch response text
        """
        self._rate_limit()
        
        params = self._build_params({
            "db": db,
            "id": id,
            "retmode": retmode,
        })
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/efetch.fcgi",
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            return response.text
    
    async def search_geo(
        self, 
        term: str, 
        retmax: Optional[int] = None,
        record_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Search GEO for all types of records.
        
        Args:
            term: Search term (e.g., 'breast cancer', 'GSE12345', 'RNA-seq')
            retmax: Maximum number of results to return
            record_types: Optional filter for specific types ["GSE", "GSM", "GPL", "GDS"]
            
        Returns:
            Dictionary with categorized results by record type
        """
        try:
            retmax = retmax or self.retmax
            
            # Search the gds database
            data = await self._esearch('gds', term, retmax)
            ids = data.get('esearchresult', {}).get('idlist', [])
            
            if not ids:
                return {
                    "total_count": 0,
                    "results": [],
                    "series": [],
                    "samples": [],
                    "platforms": [],
                    "datasets": []
                }
            
            # Get detailed summaries
            summaries = await self._esummary('gds', ids)
            results = summaries.get('result', {})
            
            # Categorize results by accession type
            categorized = {
                "total_count": len(ids),
                "results": [],
                "series": [],      # GSE records
                "samples": [],     # GSM records
                "platforms": [],   # GPL records
                "datasets": []     # GDS records
            }
            
            for uid in ids:
                if uid in results:
                    record = results[uid]
                    accession = record.get('accession', '')
                    
                    # Add to main results
                    categorized["results"].append(record)
                    
                    # Categorize by type
                    if accession.startswith('GSE'):
                        categorized["series"].append(record)
                    elif accession.startswith('GSM'):
                        categorized["samples"].append(record)
                    elif accession.startswith('GPL'):
                        categorized["platforms"].append(record)
                    elif accession.startswith('GDS'):
                        categorized["datasets"].append(record)
            
            # Filter by record types if specified
            if record_types:
                record_types = [rt.upper() for rt in record_types]
                filtered_results = []
                
                if "GSE" in record_types:
                    filtered_results.extend(categorized["series"])
                if "GSM" in record_types:
                    filtered_results.extend(categorized["samples"])
                if "GPL" in record_types:
                    filtered_results.extend(categorized["platforms"])
                if "GDS" in record_types:
                    filtered_results.extend(categorized["datasets"])
                
                categorized["results"] = filtered_results
                categorized["total_count"] = len(filtered_results)
            
            return categorized
            
        except httpx.HTTPStatusError as e:
            raise GEOSearchError(f"HTTP error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise GEOSearchError(f"Search error: {str(e)}")
    
    async def search_geo_profiles(self, term: str, retmax: Optional[int] = None) -> Dict[str, Any]:
        """Search GEO Profiles database.
        
        Args:
            term: Search term
            retmax: Maximum results to return
            
        Returns:
            GEO Profiles search results
        """
        try:
            retmax = retmax or self.retmax
            data = await self._esearch('geoprofiles', term, retmax)
            ids = data.get('esearchresult', {}).get('idlist', [])
            
            if not ids:
                return {"esummaryresult": ["Empty id list - nothing to do"]}
            
            summary = await self._esummary('geoprofiles', ids)
            return summary
            
        except Exception as e:
            raise GEOSearchError(f"GEO Profiles search error: {str(e)}")
    
    async def search_geo_datasets(self, term: str, retmax: Optional[int] = None) -> Dict[str, Any]:
        """Search GEO Datasets (GDS) specifically.
        
        Args:
            term: Search term
            retmax: Maximum results to return
            
        Returns:
            GDS search results
        """
        result = await self.search_geo(term, retmax, record_types=["GDS"])
        
        if result["datasets"]:
            formatted_result = {
                "header": {"type": "esummary", "version": "0.3"},
                "result": {
                    "uids": [r.get("uid") for r in result["datasets"]]
                }
            }
            for record in result["datasets"]:
                uid = record.get("uid")
                if uid:
                    formatted_result["result"][uid] = record
            
            return formatted_result
        else:
            return {"esummaryresult": ["Empty id list - nothing to do"]}
    
    async def search_geo_series(self, term: str, retmax: Optional[int] = None) -> Dict[str, Any]:
        """Search GEO Series (GSE) specifically.
        
        Args:
            term: Search term
            retmax: Maximum results to return
            
        Returns:
            GSE search results
        """
        result = await self.search_geo(term, retmax, record_types=["GSE"])
        
        if result["series"]:
            formatted_result = {
                "header": {"type": "esummary", "version": "0.3"},
                "result": {
                    "uids": [r.get("uid") for r in result["series"]]
                }
            }
            for record in result["series"]:
                uid = record.get("uid")
                if uid:
                    formatted_result["result"][uid] = record
            
            return formatted_result
        else:
            return {"esummaryresult": ["Empty id list - nothing to do"]}
    
    async def search_geo_samples(self, term: str, retmax: Optional[int] = None) -> Dict[str, Any]:
        """Search GEO Samples (GSM) specifically.
        
        Args:
            term: Search term
            retmax: Maximum results to return
            
        Returns:
            GSM search results
        """
        result = await self.search_geo(term, retmax, record_types=["GSM"])
        
        if result["samples"]:
            formatted_result = {
                "header": {"type": "esummary", "version": "0.3"},
                "result": {
                    "uids": [r.get("uid") for r in result["samples"]]
                }
            }
            for record in result["samples"]:
                uid = record.get("uid")
                if uid:
                    formatted_result["result"][uid] = record
            
            return formatted_result
        else:
            return {"esummaryresult": ["Empty id list - nothing to do"]}
    
    async def search_geo_platforms(self, term: str, retmax: Optional[int] = None) -> Dict[str, Any]:
        """Search GEO Platforms (GPL) specifically.
        
        Args:
            term: Search term
            retmax: Maximum results to return
            
        Returns:
            GPL search results
        """
        result = await self.search_geo(term, retmax, record_types=["GPL"])
        
        if result["platforms"]:
            formatted_result = {
                "header": {"type": "esummary", "version": "0.3"},
                "result": {
                    "uids": [r.get("uid") for r in result["platforms"]]
                }
            }
            for record in result["platforms"]:
                uid = record.get("uid")
                if uid:
                    formatted_result["result"][uid] = record
            
            return formatted_result
        else:
            return {"esummaryresult": ["Empty id list - nothing to do"]}
    
    async def get_series_info(self, gse_id: str) -> Dict[str, Any]:
        """Get detailed information about a GEO Series.
        
        Args:
            gse_id: GSE accession ID (e.g., 'GSE12345')
            
        Returns:
            Series information dictionary
        """
        try:
            # Search for the specific GSE
            data = await self._esearch('gds', f"{gse_id}[ACCN]", 1)
            ids = data.get('esearchresult', {}).get('idlist', [])
            
            if not ids:
                raise GEOSearchError(f"Series {gse_id} not found")
            
            # Get summary
            summaries = await self._esummary('gds', ids)
            result = summaries.get('result', {})
            
            if ids[0] in result:
                return result[ids[0]]
            else:
                raise GEOSearchError(f"No summary available for {gse_id}")
                
        except Exception as e:
            raise GEOSearchError(f"Error getting series info: {str(e)}")
